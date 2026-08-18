"""Canonical DDL model for the `certified-ddl-v1` profile.

This mirrors the type-name subset of `CanonicalDatabaseIr.CanonicalType` in
`engines/database-data-engine` (Java) deliberately -- this engine is a
narrower, real, certified DDL translator that could feed that engine's
`SqlNode`/`SchemaObjectNode` IR in the future, not a competing type system.

Every dataclass here is intentionally small and closed: `certified-ddl-v1` is
a fixed, precisely bounded subset of CREATE TABLE / CREATE INDEX syntax (see
`README.md`). Anything the parser encounters outside this subset must raise
`DialectError`, never be silently approximated.
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
    DECIMAL = "DECIMAL"
    CHAR = "CHAR"
    VARCHAR = "VARCHAR"
    TEXT = "TEXT"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"


@dataclass(frozen=True)
class CanonicalTypeRef:
    canonical_type: CanonicalType
    precision: int | None = None
    scale: int | None = None
    length: int | None = None


class DefaultKind(str, Enum):
    NUMBER = "NUMBER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    CURRENT_TIMESTAMP = "CURRENT_TIMESTAMP"


@dataclass(frozen=True)
class ColumnDefault:
    kind: DefaultKind
    literal: str | None = None  # unset for CURRENT_TIMESTAMP


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


class CheckOperator(str, Enum):
    EQ = "="
    NE = "<>"
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="


@dataclass(frozen=True)
class CheckComparison:
    """One leaf comparison: `column <op> literal`. `certified-ddl-v1` only
    supports CHECK constraints built from AND/OR of these -- no function
    calls, no subqueries, since function names are exactly where dialects
    diverge most (see README "Why CHECK is this narrow")."""

    column: str
    operator: CheckOperator
    literal: str
    literal_is_string: bool = False


class CheckConnector(str, Enum):
    AND = "AND"
    OR = "OR"


@dataclass(frozen=True)
class CheckConstraint:
    comparisons: tuple[CheckComparison, ...]
    connector: CheckConnector | None = None  # None when len(comparisons) == 1
    name: str | None = None

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
        if not self.columns:
            raise DialectError("CERTIFIED_DDL_EMPTY_TABLE", f"table {self.name!r} has no columns")
        names = {c.name for c in self.columns}
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
            for comparison in check.comparisons:
                if comparison.column not in names:
                    raise DialectError(
                        "CERTIFIED_DDL_UNKNOWN_COLUMN", f"CHECK references unknown column {comparison.column!r}"
                    )


@dataclass(frozen=True)
class Index:
    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False

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
        populated = sum(
            1 for v in (self.primary_key, self.unique, self.foreign_key, self.check) if v
        )
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
class AlterTable:
    table: str
    actions: tuple[AlterAction, ...]

    def __post_init__(self) -> None:
        if not self.actions:
            raise DialectError(
                "CERTIFIED_ALTER_EMPTY", f"ALTER TABLE {self.table!r} carries no action"
            )
