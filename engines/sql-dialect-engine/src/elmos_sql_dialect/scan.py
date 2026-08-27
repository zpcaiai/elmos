"""Coverage pre-check: how much of a real schema can this engine translate?

Same purpose as `engines/component-dialect-engine`'s `scan`, and written
after it for the same reason: a certified subset is only honest if its
boundary is visible BEFORE anyone commits to a migration. Without a
pre-check the only way to learn that a schema is 12% convertible is to run
the whole migration and read the wreckage.

Properties that make the number trustworthy:

  - **Parse-only.** Nothing is emitted, nothing is written, no target
    dialect is chosen. Subset membership is a property of the source.

  - **Split by the real parser.** Statements are separated by `sqlglot`
    itself, not by splitting on semicolons -- a semicolon inside a string
    literal, a `$$`-quoted function body or a `BEGIN ... END` block would
    make naive splitting silently miscount.

  - **Counted, never extrapolated.** Every number is a count of statements
    actually parsed.

  - **An UPPER BOUND, and it says so.** Parsing proves a statement is
    inside one of the active certified profiles from the SOURCE side; emission is still
    re-validated by the target dialect's strict parser during a real run.

One deliberate difference from the component scanner. There, a function
returning no JSX is a *helper* -- not a migration unit -- so it is
excluded from the denominator. Here there is no equivalent: an
`ALTER TABLE`, a view or a stored procedure IS a migration unit the
customer needs translated. Excluding it would flatter the ratio by
hiding exactly the work the engine cannot do. So everything executable
stays in the denominator, and only comments and blank statements are
dropped.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import sqlglot
from sqlglot import exp

from .advanced import (
    parse_comment,
    parse_create_view,
    parse_privilege,
    parse_procedure,
    parse_row_policy,
    parse_table_function,
    parse_trigger,
)
from .chinadb import CHINADB_TARGETS, chinadb_capabilities
from .models import (
    AddColumn,
    AddConstraint,
    AlterTable,
    CanonicalType,
    Dialect,
    DialectError,
    DropColumn,
    DropConstraint,
    RenameColumn,
    Table,
)
from .parser import (
    _parse_source_statements,
    parse_alter_table,
    parse_create_index,
    parse_create_schema,
    parse_create_table,
    parse_drop_table,
    parse_insert_statement,
    parse_update,
)
from .routine import parse_create_routine
from .statement_splitter import split_statements

FindingStatus = Literal["IN_SUBSET", "OUT_OF_SUBSET", "SCAN_ERROR"]
CoverageDisposition = Literal[
    "AUTOMATED_TRANSLATION_CANDIDATE",
    "MANUAL_MIGRATION_REQUIRED",
    "SOURCE_FORMAT_REVIEW",
    "ENGINE_DEFECT",
]

#: Directories never worth walking into.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        "target",
        "build",
        "dist",
        "out",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
    }
)

BlockerFamily = Literal[
    "statement-kind",
    "types",
    "constraints",
    "defaults",
    "identifiers",
    "structure",
    "source-format",
]

#: Plain-language meaning per reason code, plus the family it belongs to.
#:
#: Without this a coverage report is a wall of SCREAMING_SNAKE_CASE that
#: nobody can act on. Codes absent here fall back to the parser's own
#: message, which is always populated -- an unmapped code degrades to less
#: readable, never to wrong.
BLOCKER_CATALOG: dict[str, tuple[BlockerFamily, str]] = {
    "CERTIFIED_DDL_CLIENT_DIRECTIVE": (
        "source-format",
        "a psql client directive such as `\\c` or `\\i` -- it never reaches a server, so it "
        "is neither in nor out of the SQL subset; it has to be handled before translation",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "a statement no certified profile covers -- query DML and procedural control flow still land here",
    ),
    "CERTIFIED_INSERT_UNSUPPORTED_SOURCE": (
        "statement-kind",
        "the INSERT source is not a fixed VALUES row set or bounded single-source SELECT",
    ),
    "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY": (
        "statement-kind",
        "the INSERT SELECT query has joins, subqueries, ordering, limits, CTEs or another "
        "shape outside the bounded single-source route",
    ),
    "CERTIFIED_INSERT_UNSUPPORTED_MODIFIER": (
        "statement-kind",
        "an INSERT conflict, rerun, hint or other modifier needs its own target semantic route",
    ),
    "CERTIFIED_INSERT_UNSUPPORTED_EXPRESSION": (
        "types",
        "an INSERT value is an expression or typed literal outside the portable literal seed profile",
    ),
    "CERTIFIED_INSERT_UNSUPPORTED_TARGET": (
        "identifiers",
        "the INSERT target is not one plain table with an explicit column list",
    ),
    "CERTIFIED_DML_UNSUPPORTED_EXPRESSION": (
        "structure",
        "the DML value is outside the typed column/literal/timestamp/COALESCE/MIN expression core",
    ),
    "CERTIFIED_DML_UNSUPPORTED_PREDICATE": (
        "structure",
        "the DML predicate is outside the portable comparison and null-test core",
    ),
    "CERTIFIED_UPDATE_UNSUPPORTED_SOURCE": (
        "statement-kind",
        "UPDATE ... FROM or another derived row source needs a target-specific route",
    ),
    "CERTIFIED_UPDATE_SOURCE_KEY_UNPROVEN": (
        "structure",
        "an UPDATE row source has no source-schema proof that its join columns are unique",
    ),
    "CERTIFIED_UPDATE_SOURCE_KEY_NOT_UNIQUE": (
        "structure",
        "an UPDATE row source can match a target row more than once because its join columns are not a declared key",
    ),
    "CERTIFIED_UPDATE_COLUMN_TYPE_UNPROVEN": (
        "types",
        "an UPDATE row-source assignment lacks matching typed source and target catalogue facts",
    ),
    "CERTIFIED_UPDATE_UNSUPPORTED_MODIFIER": (
        "statement-kind",
        "UPDATE ordering, limiting or CTE semantics are outside the bounded route",
    ),
    "CERTIFIED_UPDATE_UNSUPPORTED_ASSIGNMENT": (
        "structure",
        "UPDATE assignments must be plain target columns with typed values",
    ),
    "CERTIFIED_UPDATE_EMPTY": ("structure", "an UPDATE has no assignments"),
    "CERTIFIED_UPDATE_DUPLICATE_TARGET": (
        "structure",
        "an UPDATE assigns the same target column more than once",
    ),
    "CERTIFIED_UPDATE_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "not a single UPDATE statement",
    ),
    "CERTIFIED_ROUTINE_PROCEDURE_UNSUPPORTED": (
        "statement-kind",
        "a stored procedure needs an exact target/version/transaction/side-effect route; "
        "it is not converted as a scalar function",
    ),
    "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED": (
        "statement-kind",
        "a trigger needs target-specific timing, row/statement and transition-value semantics",
    ),
    "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE": (
        "structure",
        "only a table-free SQL expression function is in the portable routine profile; "
        "PL/pgSQL and other routine languages remain explicit blockers",
    ),
    "CERTIFIED_ROUTINE_UNSUPPORTED_BODY": (
        "structure",
        "the function body is not one table-free SELECT expression in the typed routine IR",
    ),
    "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION": (
        "structure",
        "a function call or code point form is outside the portable routine expression allowlist",
    ),
    "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER": (
        "structure",
        "routine parameters must have one plain name, one typed input value and no default/mode/constraint",
    ),
    "CERTIFIED_ROUTINE_UNSUPPORTED_OPERATOR": (
        "structure",
        "routine arithmetic or concatenation uses operands whose canonical types are not portable",
    ),
    "CERTIFIED_ROUTINE_RETURN_TYPE_MISMATCH": (
        "types",
        "the typed routine body result does not match the declared canonical return type",
    ),
    "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED": (
        "structure",
        "RETURNS TABLE needs a typed row-shape IR and is not a scalar routine",
    ),
    "CERTIFIED_ROUTINE_NAMESPACE_MAPPING_REQUIRED": (
        "identifiers",
        "a qualified routine name needs an explicit target namespace mapping",
    ),
    "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET": (
        "statement-kind",
        "CREATE OR REPLACE rerun and ownership semantics have no one exact spelling across targets",
    ),
    "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED": (
        "statement-kind",
        "row-level security needs a target policy model and execution evidence; "
        "it is never lowered to a permissive policy",
    ),
    "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED": (
        "structure",
        "SECURITY DEFINER or SET search_path changes execution identity/name resolution and needs an exact mapping",
    ),
    "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET": (
        "structure",
        "STRICT null short-circuiting is routine metadata and is not silently approximated",
    ),
    "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET": (
        "structure",
        "routine volatility/stability has no one exact cross-dialect mapping in this profile",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "not a single ALTER TABLE statement",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_ACTION": (
        "statement-kind",
        "an ALTER TABLE action outside ADD/DROP/RENAME COLUMN and ADD/DROP CONSTRAINT -- "
        "column type, nullability and default changes need the column's full type, which a "
        "single ALTER statement does not carry",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT_MODIFIER": (
        "statement-kind",
        "an ALTER TABLE modifier outside the certified set (IF EXISTS and similar)",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT": (
        "constraints",
        "an ADD CONSTRAINT clause outside PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK",
    ),
    "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT": (
        "constraints",
        "an inline PRIMARY KEY or UNIQUE on an added column -- the dialects differ on whether "
        "that may be combined with ADD COLUMN, so add the column and the constraint separately",
    ),
    "CERTIFIED_ALTER_MISSING_TYPE": ("types", "an added column with no type"),
    "CERTIFIED_ALTER_EMPTY": ("structure", "an ALTER TABLE carrying no action"),
    "CERTIFIED_DDL_MULTIPLE_STATEMENTS": (
        "statement-kind",
        "more than one statement handed to a single translate call",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER": (
        "statement-kind",
        "a modifier on the statement outside the certified set (IF NOT EXISTS, "
        "TEMPORARY, table options, tablespaces, and similar)",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_TYPE": (
        "types",
        "a column type outside the certified cross-dialect set",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_TYPE_PARAM": (
        "types",
        "a type parameter outside the certified set (precision/scale/charset variants)",
    ),
    "CERTIFIED_DDL_UNREACHABLE_TYPE": (
        "types",
        "a type this engine cannot render on every target dialect",
    ),
    "CERTIFIED_DDL_UNBOUNDED_VARCHAR": (
        "types",
        "a VARCHAR with no length -- unlimited in PostgreSQL, VARCHAR(1) in SQL Server, "
        "rejected outright by MySQL and Oracle; declare an explicit length",
    ),
    "CERTIFIED_DDL_UNBOUNDED_DECIMAL": (
        "types",
        "a DECIMAL/NUMBER with no precision -- arbitrary precision in PostgreSQL and Oracle, "
        "with no fixed-precision equivalent on MySQL or SQL Server",
    ),
    "CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE": (
        "types",
        "a BIGINT UNSIGNED column -- its range reaches 18446744073709551615, which no "
        "canonical integer holds and which PostgreSQL, Oracle and SQL Server cannot express",
    ),
    "CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY": (
        "structure",
        "an identity/auto-increment column that is not a key -- legal in PostgreSQL, Oracle "
        "and SQL Server, rejected by MySQL with errno 1075",
    ),
    "CERTIFIED_DDL_LENGTH_EXCEEDS_TARGET": (
        "types",
        "a CHAR/VARCHAR length the target dialect's documented maximum does not allow",
    ),
    "CERTIFIED_DDL_PRECISION_EXCEEDS_TARGET": (
        "types",
        "a DECIMAL precision or scale the target dialect's documented maximum does not allow",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_COLUMN_CONSTRAINT": (
        "constraints",
        "a column constraint outside NOT NULL / PRIMARY KEY / UNIQUE / DEFAULT / CHECK / REFERENCES",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT": (
        "constraints",
        "a table-level constraint outside the certified set",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_CHECK": (
        "constraints",
        "a CHECK expression outside the typed portable boolean, comparison, interval, regex and LIKE core",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN": (
        "constraints",
        "a regex CHECK pattern outside the portable cross-dialect regex core",
    ),
    "CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX": (
        "constraints",
        "a MySQL regex predicate whose case sensitivity is inherited from collation",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER": (
        "constraints",
        "a regex match parameter whose flags cannot be preserved across targets",
    ),
    "CERTIFIED_DDL_REGEX_CHECK_UNREACHABLE_ON_TARGET": (
        "constraints",
        "SQL Server has no regex CHECK predicate; only a bounded ASCII subset has a proven binary-collation lowering",
    ),
    "CERTIFIED_DDL_MULTI_LEVEL_CHECK": (
        "constraints",
        "a CHECK boolean tree deeper than the bounded canonical form",
    ),
    "CERTIFIED_DDL_EMPTY_CHECK": ("constraints", "a CHECK with no comparison in it"),
    "CERTIFIED_DDL_MISSING_CONNECTOR": (
        "constraints",
        "a multi-comparison CHECK with no single AND/OR connector",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_REFERENTIAL_ACTION": (
        "constraints",
        "an ON DELETE / ON UPDATE action outside the certified set",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_DEFAULT": (
        "defaults",
        "a DEFAULT that is not a plain literal -- function calls like now() and "
        "expressions land here, because their spelling and semantics differ per dialect",
    ),
    "CERTIFIED_DDL_DEFAULT_TYPE_MISMATCH": (
        "defaults",
        "a DEFAULT literal whose type disagrees with the declared column type",
    ),
    "CERTIFIED_DDL_UNREACHABLE_DEFAULT": (
        "defaults",
        "a DEFAULT this engine cannot render on every target dialect",
    ),
    "CERTIFIED_DDL_QUALIFIED_TABLE_NAME": (
        "identifiers",
        "a schema- or database-qualified name; qualification rules differ per dialect",
    ),
    "CERTIFIED_DDL_QUOTED_IDENTIFIER": (
        "identifiers",
        "a quoted identifier -- quoting character and case-folding differ per dialect",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE": (
        "identifiers",
        "an identifier outside a plain unquoted [A-Za-z_][A-Za-z0-9_]* name",
    ),
    "CERTIFIED_DDL_MISSING_IDENTIFIER": ("identifiers", "a missing table, column or index name"),
    "CERTIFIED_DDL_UNKNOWN_COLUMN": (
        "structure",
        "a constraint or index referencing a column the statement never declares",
    ),
    "CERTIFIED_DDL_DUPLICATE_COLUMN": ("structure", "the same column declared twice"),
    "CERTIFIED_DDL_EMPTY_TABLE": ("structure", "a CREATE TABLE with no columns"),
    "CERTIFIED_DDL_EMPTY_INDEX": ("structure", "a CREATE INDEX with no columns"),
    "CERTIFIED_DDL_UNSUPPORTED_INDEX_MODIFIER": (
        "structure",
        "a CREATE INDEX modifier such as WHERE, INCLUDE or USING has no common exact spelling",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_INDEX_ORDER": (
        "structure",
        "an index NULLS placement cannot be preserved across the four target dialects",
    ),
    "CERTIFIED_DDL_UNSUPPORTED_TABLE_ITEM": (
        "structure",
        "an item inside CREATE TABLE that is neither a column nor a certified constraint",
    ),
    "CERTIFIED_DDL_PARSE_FAILED": (
        "source-format",
        "sqlglot rejected the statement under the declared source dialect -- a syntax "
        "error, or dialect-specific syntax the reader does not accept",
    ),
    "CERTIFIED_DROP_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "not a single DROP TABLE statement",
    ),
    "CERTIFIED_DROP_UNSUPPORTED_MODIFIER": (
        "statement-kind",
        "DROP TABLE carries dependency or temporary-object semantics outside the portable profile",
    ),
    "CERTIFIED_DROP_IF_EXISTS_UNSUPPORTED_BY_TARGET": (
        "statement-kind",
        "DROP TABLE IF EXISTS cannot be represented with the target's exact rerun semantics",
    ),
    "CERTIFIED_SCHEMA_UNSUPPORTED_STATEMENT": (
        "statement-kind",
        "not a single minimal CREATE SCHEMA statement",
    ),
    "CERTIFIED_SCHEMA_UNSUPPORTED_MODIFIER": (
        "statement-kind",
        "CREATE SCHEMA carries options outside the portable profile",
    ),
    "CERTIFIED_SCHEMA_QUALIFIED_NAME": (
        "identifiers",
        "a schema declaration with more than one namespace component",
    ),
    "CERTIFIED_VIEW_UNSUPPORTED_QUERY": (
        "statement-kind",
        "the view needs a typed query route beyond the single-table bounded SELECT profile",
    ),
    "CERTIFIED_VIEW_REPLACE_UNSUPPORTED_BY_TARGET": (
        "statement-kind",
        "CREATE OR REPLACE VIEW requires a target/version-specific rerun policy",
    ),
    "CERTIFIED_COMMENT_TARGET_UNSUPPORTED": (
        "statement-kind",
        "the target stores comments through a different ownership/property mechanism",
    ),
    "CERTIFIED_COMMENT_TARGET_SCHEMA_REQUIRED": (
        "identifiers",
        "SQL Server extended properties require an explicit target schema mapping",
    ),
    "CERTIFIED_COMMENT_TARGET_VALUE_TOO_LARGE": (
        "statement-kind",
        "the SQL Server extended-property value exceeds its 7,500-byte limit",
    ),
    "CERTIFIED_COMMENT_TARGET_COLUMN_TYPE_REQUIRED": (
        "types",
        "MySQL column comments require the complete target column definition, not only a comment statement",
    ),
    "CERTIFIED_PRIVILEGE_UNSUPPORTED_OBJECT": (
        "structure",
        "the privilege target is not a table in the bounded privilege route",
    ),
    "CERTIFIED_PRIVILEGE_UNSUPPORTED_KIND": (
        "structure",
        "the privilege or grant option requires a target-specific security policy",
    ),
    "CERTIFIED_PRIVILEGE_ROUTINE_SIGNATURE_REQUIRED": (
        "identifiers",
        "a non-PostgreSQL target cannot safely erase a source routine signature without "
        "a target routine-identity catalogue",
    ),
    "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED": (
        "structure",
        "trigger action/timing/order semantics require a target-specific trigger route",
    ),
    "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED": (
        "types",
        "JSONB storage, operator, indexing, and ordering semantics cannot be downgraded to plain JSON",
    ),
    "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED": (
        "types",
        "array storage and element semantics require a target-specific collection mapping",
    ),
    "CERTIFIED_DDL_BINARY_LENGTH_ENFORCEMENT_UNSUPPORTED": (
        "types",
        "the target binary type does not enforce the source length contract",
    ),
}


@dataclass(frozen=True)
class ScanFinding:
    source_path: str
    #: 1-based position of the statement within its file.
    statement_index: int
    status: FindingStatus
    #: The statement kind sqlglot identified, e.g. "Create", "Alter", "Insert".
    statement_kind: str | None
    reason_code: str | None
    reason: str | None
    family: str | None
    #: First line of the statement, trimmed -- enough to recognise it.
    excerpt: str
    #: Every discovered unit receives one explicit disposition. This is the
    #: 100% repository-coverage measure; it is deliberately separate from
    #: `IN_SUBSET`, which is only an upper bound for automatic translation.
    disposition: CoverageDisposition


@dataclass(frozen=True)
class BlockerGroup:
    reason_code: str
    family: str | None
    what: str
    #: Total blocked statements carrying this code.
    count: int
    #: How many DISTINCT reasons produced that count.
    #:
    #: This is the number that should drive a roadmap, and it is why the
    #: two are reported separately. On the first real scan a single
    #: copy-pasted idiom -- `CHECK (h IS NULL OR h ~ '^[0-9a-f]{64}$')` --
    #: accounted for 340 of 342 occurrences of one blocker. Ranking by
    #: occurrences alone would have pointed the next expansion at a problem
    #: that is really one line of SQL repeated across a schema.
    distinct_reasons: int
    share_of_blocked: float
    example_statements: list[str]


@dataclass(frozen=True)
class FamilyGroup:
    family: str
    count: int
    share_of_blocked: float


@dataclass(frozen=True)
class FeasibilityReport:
    schema_version: str
    kind: str
    profile: str
    repository: str
    source_dialect: str
    scanned_at: str
    totals: dict[str, int]
    upper_bound_coverage: float
    disposition_coverage: float
    disposition_counts: dict[str, int]
    blockers: list[BlockerGroup]
    families: list[FamilyGroup]
    findings: list[ScanFinding]
    caveats: list[str] = field(default_factory=list)
    chinadb_coverage: dict[str, object] = field(default_factory=dict)


def discover_sql_files(repository: str | os.PathLike[str]) -> list[Path]:
    """Every `.sql` file under `repository`, sorted, skipping build output."""
    root = Path(repository)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRECTORIES]
        for name in filenames:
            if name.endswith(".sql"):
                found.append(Path(dirpath) / name)
    return sorted(found)


def _excerpt(statement: exp.Expr) -> str:
    text = statement.sql().strip().replace("\n", " ")
    return text[:110] + ("..." if len(text) > 110 else "")


def _disposition(status: FindingStatus, reason_code: str | None) -> CoverageDisposition:
    """Map every scanner outcome to an auditable next action.

    A blocker is not silently treated as converted: it remains an explicit
    manual migration requirement. Parser/file issues are source-format work,
    and unexpected scanner exceptions remain engine defects. Only statements
    admitted by the certified parser are automatic-translation candidates.
    """
    if status == "IN_SUBSET":
        return "AUTOMATED_TRANSLATION_CANDIDATE"
    if reason_code in {
        "CERTIFIED_DDL_CLIENT_DIRECTIVE",
        "CERTIFIED_DDL_PARSE_FAILED",
        "CERTIFIED_DDL_MULTIPLE_STATEMENTS",
        "FILE_UNREADABLE",
    }:
        return "SOURCE_FORMAT_REVIEW"
    if status == "SCAN_ERROR":
        return "ENGINE_DEFECT"
    return "MANUAL_MIGRATION_REQUIRED"


def _catalog_key(schema: str | None, table: str) -> tuple[str, str]:
    return ((schema or "").casefold(), table.casefold())


@dataclass
class SourceSchemaCatalog:
    """Typed source facts used to prove bounded UPDATE row-source safety.

    This catalogue is built from the migration source, never from a live
    database.  A source UPDATE may use a table as its row source only when
    the exact source join columns are a declared PRIMARY KEY or UNIQUE key.
    Dropping an unknown constraint invalidates the table's recorded keys,
    which is conservative: absent evidence is never treated as uniqueness.
    """

    columns: dict[tuple[str, str], dict[str, CanonicalType]] = field(default_factory=dict)
    unique_keys: dict[tuple[str, str], set[tuple[str, ...]]] = field(default_factory=dict)

    def add_table(self, table: Table) -> None:
        key = _catalog_key(table.schema, table.name)
        self.columns[key] = {
            column.name.casefold(): column.type_ref.canonical_type for column in table.columns
        }
        self.unique_keys[key] = {
            tuple(column.casefold() for column in table.primary_key),
            *(tuple(column.casefold() for column in unique) for unique in table.unique_constraints),
        } - {()}

    def apply_alter(self, alter: AlterTable) -> None:
        key = _catalog_key(alter.schema, alter.table)
        columns = self.columns.setdefault(key, {})
        keys = self.unique_keys.setdefault(key, set())
        for action in alter.actions:
            if isinstance(action, AddColumn):
                columns[action.column.name.casefold()] = action.column.type_ref.canonical_type
            elif isinstance(action, DropColumn):
                name = action.column.casefold()
                columns.pop(name, None)
                keys.difference_update({candidate for candidate in keys if name in candidate})
            elif isinstance(action, RenameColumn):
                old = action.column.casefold()
                new = action.new_name.casefold()
                column_type = columns.pop(old, None)
                if column_type is not None:
                    columns[new] = column_type
                keys_copy = list(keys)
                keys.clear()
                for candidate in keys_copy:
                    keys.add(tuple(new if item == old else item for item in candidate))
            elif isinstance(action, AddConstraint):
                if action.primary_key:
                    keys.add(tuple(column.casefold() for column in action.primary_key))
                if action.unique:
                    keys.add(tuple(column.casefold() for column in action.unique))
            elif isinstance(action, DropConstraint):
                # The certified alter IR intentionally does not preserve the
                # dropped constraint's old shape. Invalidate all uniqueness
                # facts rather than guessing which one was removed.
                keys.clear()

    def _matching_keys(self, schema: str | None, table: str) -> list[tuple[str, str]]:
        if schema is not None:
            return [_catalog_key(schema, table)]
        return [key for key in self.columns if key[1] == table.casefold()]

    def type_of(self, table: str, column: str) -> CanonicalType | None:
        matches = [self.columns[key].get(column.casefold()) for key in self._matching_keys(None, table)]
        present = [item for item in matches if item is not None]
        return present[0] if len(present) == 1 else None

    def has_unique_key(self, schema: str | None, table: str, columns: tuple[str, ...]) -> bool:
        wanted = tuple(column.casefold() for column in columns)
        matches = self._matching_keys(schema, table)
        return len(matches) == 1 and wanted in self.unique_keys.get(matches[0], set())


def _record_catalog_statement(
    catalog: SourceSchemaCatalog,
    statement: exp.Expression,
    dialect: Dialect,
    namespace_map: Mapping[str, str] | None,
) -> None:
    """Add only source statements whose typed schema facts parse cleanly."""
    try:
        if isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TABLE":
            catalog.add_table(parse_create_table(statement, dialect, namespace_map))
        elif isinstance(statement, exp.Alter):
            catalog.apply_alter(parse_alter_table(statement, dialect, namespace_map))
    except DialectError:
        # A target- or statement-specific blocker must not turn into schema
        # evidence.  The next UPDATE then remains fail-closed.
        return


def _classify(
    statement: exp.Expr,
    dialect: Dialect,
    raw_sql: str | None = None,
    namespace_map: Mapping[str, str] | None = None,
    catalog: SourceSchemaCatalog | None = None,
) -> tuple[FindingStatus, str | None, str | None]:
    """Parse one statement through the real certified parser.

    Returns ``(status, reason_code, reason)``. A `DialectError` is a subset
    boundary; anything else is an engine defect and is reported as such
    rather than being folded into the blocked count.
    """
    # The parsed node goes straight through. Serialising it back to SQL so the
    # parser could parse it a second time was two thirds of the work here, and
    # the round trip could only lose fidelity relative to the node the splitter
    # already produced.
    #
    # sqlglot's stubs type a parsed statement as an internal `Expr` alias that
    # is not assignable to `Expression` (see the same note in `parser.py`), so
    # narrow it here. The runtime object is an `Expression`; `Expr` only ever
    # appears in annotations, which this module never evaluates.
    assert isinstance(statement, exp.Expression)
    try:
        # A file-level parse can leave one unusual PostgreSQL ALTER as an
        # opaque Command while the raw statement is still recoverable by the
        # narrow multi-action compatibility path. Reparse only that raw unit;
        # ordinary commands remain commands and therefore fail closed below.
        if isinstance(statement, exp.Command) and raw_sql is not None:
            try:
                recovered = _parse_source_statements(raw_sql, dialect)
            except sqlglot.errors.SqlglotError:
                recovered = []
            if len(recovered) == 1 and not isinstance(recovered[0], exp.Command):
                statement = recovered[0]
        if isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TABLE":
            parse_create_table(statement, dialect, namespace_map)
        elif isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "INDEX":
            parse_create_index(raw_sql or statement, dialect, namespace_map)
        elif isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "SCHEMA":
            parse_create_schema(statement, dialect, namespace_map)
        elif isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "VIEW":
            parse_create_view(raw_sql or statement, dialect, namespace_map)
        elif isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() in {
            "FUNCTION",
            "PROCEDURE",
        }:
            if str(statement.args.get("kind", "")).upper() == "PROCEDURE":
                parse_procedure(raw_sql or statement, dialect, namespace_map)
            else:
                try:
                    parse_table_function(raw_sql or statement, dialect, namespace_map)
                except DialectError as exc:
                    if exc.code != "CERTIFIED_ROUTINE_NOT_TABLE_FUNCTION":
                        raise
                    parse_create_routine(raw_sql or statement, dialect, namespace_map)
        elif isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TRIGGER":
            parse_trigger(raw_sql or statement, dialect, namespace_map)
        elif isinstance(statement, exp.Comment):
            parse_comment(raw_sql or statement, dialect, namespace_map)
        elif isinstance(statement, exp.Grant | exp.Revoke):
            parse_privilege(raw_sql or statement, dialect, namespace_map)
        elif (
            isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "POLICY"
        ) or (raw_sql is not None and raw_sql.lstrip().upper().startswith("CREATE POLICY")):
            parse_row_policy(raw_sql or statement, dialect)
        elif isinstance(statement, exp.Alter):
            # certified-alter-v1. Routed here so the coverage number tracks
            # what the engine can really do rather than one profile of it.
            parse_alter_table(statement, dialect)
        elif isinstance(statement, exp.Drop):
            parse_drop_table(statement, dialect)
        elif isinstance(statement, exp.Insert):
            parse_insert_statement(raw_sql or statement, dialect, namespace_map)
        elif isinstance(statement, exp.Update):
            parse_update(raw_sql or statement, dialect, namespace_map, catalog)
        else:
            # Not covered by any certified DDL profile. This is the single
            # most important number in the report, so it is produced by the
            # same fail-closed path as everything else rather than by a
            # special case that could drift from the parser.
            parse_create_table(statement, dialect)
        return "IN_SUBSET", None, None
    except DialectError as exc:
        return "OUT_OF_SUBSET", exc.code, exc.message
    except Exception as exc:  # noqa: BLE001 - deliberately broad; see below
        # NOT a subset boundary -- a defect in this engine. Kept separate so
        # a crash can never be laundered into a coverage percentage.
        return "SCAN_ERROR", "ENGINE_ERROR", f"{type(exc).__name__}: {exc}"


def _recover_statements(
    text: str,
    relative: str,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
    catalog: SourceSchemaCatalog | None = None,
) -> list[ScanFinding]:
    """Classify a file the parser refused as a whole, statement by statement.

    Each statement is handed to the same parser independently, so the ones it
    can read are judged exactly as they would be in a file that parsed, and
    only the ones it cannot are reported as unreadable -- with their own line
    number, so they can be found.

    psql client directives (``\\c``, ``\\i``, ``\\.``) get their own code. They are
    not SQL, never reach a server, and calling them a parse failure would
    misattribute a client-side construct to the dialect grammar.
    """

    findings: list[ScanFinding] = []
    for index, raw in enumerate(split_statements(text), start=1):
        excerpt = raw.text.strip().replace("\n", " ")[:110]
        if raw.text.lstrip().startswith("\\"):
            findings.append(
                ScanFinding(
                    relative,
                    index,
                    "OUT_OF_SUBSET",
                    None,
                    "CERTIFIED_DDL_CLIENT_DIRECTIVE",
                    f"line {raw.start_line}: psql client directive, not a SQL statement",
                    "source-format",
                    excerpt,
                    "SOURCE_FORMAT_REVIEW",
                )
            )
            continue
        try:
            parsed = _parse_source_statements(raw.text, source_dialect)
        except Exception as exc:  # noqa: BLE001 - sqlglot raises several types
            findings.append(
                ScanFinding(
                    relative,
                    index,
                    "OUT_OF_SUBSET",
                    None,
                    "CERTIFIED_DDL_PARSE_FAILED",
                    f"line {raw.start_line}: {source_dialect.value} parser rejected the statement: {exc}",
                    "source-format",
                    excerpt,
                    "SOURCE_FORMAT_REVIEW",
                )
            )
            continue
        if len(parsed) != 1:
            findings.append(
                ScanFinding(
                    relative,
                    index,
                    "OUT_OF_SUBSET",
                    None,
                    "CERTIFIED_DDL_MULTIPLE_STATEMENTS",
                    f"line {raw.start_line}: recovered chunk holds {len(parsed)} statements",
                    "structure",
                    excerpt,
                    "SOURCE_FORMAT_REVIEW",
                )
            )
            continue
        statement = parsed[0]
        status, code, reason = _classify(statement, source_dialect, raw.text, namespace_map, catalog)
        family = BLOCKER_CATALOG.get(code or "", (None, ""))[0] if code else None
        findings.append(
            ScanFinding(
                relative,
                index,
                status,
                type(statement).__name__,
                code,
                reason,
                family,
                _excerpt(statement),
                _disposition(status, code),
            )
        )
        if catalog is not None:
            _record_catalog_statement(catalog, statement, source_dialect, namespace_map)
    return findings


def scan_repository(
    repository: str | os.PathLike[str],
    source_dialect: Dialect,
    examples_per_blocker: int = 5,
    include_all_findings: bool = False,
    namespace_map: Mapping[str, str] | None = None,
) -> FeasibilityReport:
    """Parse every statement in every `.sql` file and report subset membership."""
    root = Path(repository)
    if not root.exists():
        raise DialectError("REPOSITORY_NOT_FOUND", str(root))

    findings: list[ScanFinding] = []
    catalog = SourceSchemaCatalog()
    for path in discover_sql_files(root):
        relative = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                ScanFinding(
                    relative,
                    0,
                    "SCAN_ERROR",
                    None,
                    "FILE_UNREADABLE",
                    str(exc),
                    None,
                    "",
                    _disposition("SCAN_ERROR", "FILE_UNREADABLE"),
                )
            )
            continue

        # Split with the REAL parser. Splitting on ";" would miscount any
        # file containing a semicolon inside a string literal, a $$-quoted
        # body, or a BEGIN ... END block.
        try:
            statements = _parse_source_statements(text, source_dialect)
        except Exception:  # noqa: BLE001 - sqlglot raises several types
            # ONE construct the parser cannot read must not discard the file.
            # Measured, five files lost 750 KB of real schema this way, and
            # each of the five had exactly one offending statement -- while
            # every coverage ratio was flattered, because those files
            # contributed 1 to the denominator instead of hundreds.
            findings.extend(_recover_statements(text, relative, source_dialect, namespace_map, catalog))
            continue

        index = 0
        raw_statements = list(split_statements(text))
        raw_by_index = raw_statements if len(raw_statements) == len(statements) else []
        for statement in statements:
            if statement is None:
                continue  # a comment or trailing separator, not a statement
            index += 1
            raw_sql = raw_by_index[index - 1].text if raw_by_index else None
            status, code, reason = _classify(statement, source_dialect, raw_sql, namespace_map, catalog)
            family = BLOCKER_CATALOG.get(code or "", (None, ""))[0] if code else None
            findings.append(
                ScanFinding(
                    relative,
                    index,
                    status,
                    type(statement).__name__,
                    code,
                    reason,
                    family,
                    _excerpt(statement),
                    _disposition(status, code),
                )
            )
            _record_catalog_statement(catalog, statement, source_dialect, namespace_map)

    return _build_report(root, source_dialect, findings, examples_per_blocker, include_all_findings)


def _distinct_examples(group: list[ScanFinding], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for finding in group:
        key = finding.reason or finding.excerpt
        if key in seen:
            continue
        seen.add(key)
        out.append(finding.excerpt)
        if len(out) >= limit:
            break
    return out


def _build_report(
    root: Path,
    source_dialect: Dialect,
    findings: list[ScanFinding],
    examples_per_blocker: int,
    include_all_findings: bool,
) -> FeasibilityReport:
    in_subset = sum(1 for f in findings if f.status == "IN_SUBSET")
    blocked = [f for f in findings if f.status == "OUT_OF_SUBSET"]
    scan_errors = sum(1 for f in findings if f.status == "SCAN_ERROR")
    denominator = in_subset + len(blocked)
    disposition_counts: dict[str, int] = {}
    for finding in findings:
        disposition_counts[finding.disposition] = disposition_counts.get(finding.disposition, 0) + 1
    disposition_units = len(findings)
    disposition_covered = sum(disposition_counts.values())
    disposition_coverage = round(disposition_covered / disposition_units, 3) if disposition_units else 0.0

    by_code: dict[str, list[ScanFinding]] = {}
    for finding in blocked:
        by_code.setdefault(finding.reason_code or "UNKNOWN", []).append(finding)

    blockers = [
        BlockerGroup(
            reason_code=code,
            family=BLOCKER_CATALOG.get(code, (None, ""))[0],
            what=BLOCKER_CATALOG.get(code, (None, group[0].reason or "no description available"))[1],
            count=len(group),
            distinct_reasons=len({f.reason for f in group}),
            share_of_blocked=round(len(group) / len(blocked), 3) if blocked else 0.0,
            # Deduplicated, so the examples show distinct problems rather
            # than the same line quoted five times.
            example_statements=_distinct_examples(group, examples_per_blocker),
        )
        for code, group in by_code.items()
    ]
    # Frequency first; ties broken by code so the report is deterministic
    # and diffable across runs.
    blockers.sort(key=lambda b: (-b.count, b.reason_code))

    family_counts: dict[str, int] = {}
    for finding in blocked:
        if finding.family:
            family_counts[finding.family] = family_counts.get(finding.family, 0) + 1
    families = [
        FamilyGroup(name, count, round(count / len(blocked), 3) if blocked else 0.0)
        for name, count in family_counts.items()
    ]
    families.sort(key=lambda f: (-f.count, f.family))

    caveats = [
        "This is an UPPER BOUND. Parsing proves a statement is inside certified-ddl-v1 from the SOURCE "
        "side. During a real run each emission is re-parsed by the TARGET dialect in strict mode, and a "
        "statement can still be reported BLOCKED there.",
        "Counts are exact -- every statement was really parsed by sqlglot and by this engine's certified "
        "parser. Nothing is sampled or extrapolated.",
        f"Disposition coverage is {disposition_covered}/{disposition_units} ({disposition_coverage:.1%}): "
        "every discovered unit has an explicit next action. This is not a claim that every unit is "
        "automatically translatable; the automatic-translation candidate ratio remains the separate "
        "upper-bound metric above.",
        "Read the `Distinct` column, not just the count. A blocker with 342 occurrences but 3 distinct "
        "reasons is one idiom repeated across a schema; widening the subset for it buys far less than the "
        "raw count suggests, and ranking by occurrences alone would misdirect the roadmap.",
        "Statements are split by the real parser, not by semicolons, so string literals, $$-quoted bodies "
        "and BEGIN ... END blocks are counted correctly.",
        "Everything executable stays in the denominator. Unlike the component scanner -- where a function "
        "returning no JSX is a helper rather than a migration unit -- an ALTER TABLE, view or stored "
        "procedure IS work the customer needs done, so excluding it would flatter the ratio by hiding "
        "exactly what this engine cannot do.",
    ]

    # ChinaDB target renderers are not registered in this standalone engine.
    # Still account for every source unit against every exact domestic target
    # so the coverage ledger cannot silently omit that part of the migration.
    # An admitted source statement is therefore an explicit target-adapter
    # review, not an automatic conversion claim.
    domestic_disposition_counts = {
        "TARGET_ADAPTER_REVIEW_REQUIRED": disposition_counts.get(
            "AUTOMATED_TRANSLATION_CANDIDATE", 0
        ),
        "MANUAL_MIGRATION_REQUIRED": disposition_counts.get("MANUAL_MIGRATION_REQUIRED", 0),
        "SOURCE_FORMAT_REVIEW": disposition_counts.get("SOURCE_FORMAT_REVIEW", 0),
        "ENGINE_DEFECT": disposition_counts.get("ENGINE_DEFECT", 0),
    }
    domestic_source_units = len(findings)
    domestic_route_units = domestic_source_units * len(CHINADB_TARGETS)
    domestic_source_route_covered = sum(domestic_disposition_counts.values())
    domestic_route_covered = domestic_source_route_covered * len(CHINADB_TARGETS)
    domestic_route_coverage = (
        round(domestic_route_covered / domestic_route_units, 3) if domestic_route_units else 0.0
    )
    domestic_target_rows = [
        {
            "targetId": target.id,
            "label": target.label,
            "routeDispositionUnits": domestic_source_units,
            "routeDispositionCovered": domestic_source_route_covered,
            "routeDispositionUnknown": domestic_source_units - domestic_source_route_covered,
            "routeDispositionCoverage": domestic_route_coverage,
            "sourceAutomaticCandidates": in_subset,
            "automaticTargetEmissions": 0,
            "targetAdapterReviewRequired": in_subset,
            "manualMigrationRequired": domestic_disposition_counts["MANUAL_MIGRATION_REQUIRED"],
            "sourceFormatReview": domestic_disposition_counts["SOURCE_FORMAT_REVIEW"],
            "engineDefects": domestic_disposition_counts["ENGINE_DEFECT"],
            "targetSqlEmission": "PROHIBITED_UNTIL_EXACT_ADAPTER_AND_EVIDENCE",
            "externalExecution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for target in CHINADB_TARGETS
    ]
    chinadb_coverage = chinadb_capabilities()
    chinadb_coverage.update(
        {
            "sourceUnits": domestic_source_units,
            "routeUnits": domestic_route_units,
            "routeDispositionCovered": domestic_route_covered,
            "routeDispositionUnknown": domestic_route_units - domestic_route_covered,
            "routeDispositionCoverage": domestic_route_coverage,
            "dispositionCounts": domestic_disposition_counts,
            "automaticTargetEmissions": 0,
            "targets": domestic_target_rows,
        }
    )
    caveats.append(
        "ChinaDB coverage is a route-disposition ledger: all exact domestic target identities are "
        "counted, but no compatibility label is treated as an exact renderer. Admitted source units "
        "remain TARGET_ADAPTER_REVIEW_REQUIRED until a versioned target adapter and independent "
        "evidence exist."
    )
    if scan_errors:
        caveats.insert(
            0,
            f"{scan_errors} statement(s) produced SCAN_ERROR. Those are engine defects, NOT subset "
            "boundaries, and they are excluded from the blocker ranking. Please report them.",
        )

    return FeasibilityReport(
        schema_version="1.0",
        kind="elmos.sql-dialect-feasibility-scan",
        profile=(
            "certified-ddl-v1 + certified-alter-v1 + certified-drop-v1 + certified-schema-v1 "
            "+ certified-routine-v1 + certified-view-v1 + certified-comment-v1 "
            "+ certified-privilege-v1 + certified-dml-v1 + certified-rls-v1"
        ),
        repository=str(root.resolve()),
        source_dialect=source_dialect.value,
        scanned_at=datetime.now(UTC).isoformat(),
        totals={
            "discovered": denominator,
            "inSubset": in_subset,
            "outOfSubset": len(blocked),
            "scanErrors": scan_errors,
            "files": len({f.source_path for f in findings}),
            "dispositionUnits": disposition_units,
            "dispositionCovered": disposition_covered,
            "dispositionUnknown": disposition_units - disposition_covered,
        },
        upper_bound_coverage=round(in_subset / denominator, 3) if denominator else 0.0,
        disposition_coverage=disposition_coverage,
        disposition_counts=dict(sorted(disposition_counts.items())),
        blockers=blockers,
        families=families,
        findings=findings if include_all_findings else [f for f in findings if f.status != "IN_SUBSET"],
        caveats=caveats,
        chinadb_coverage=chinadb_coverage,
    )


def report_to_dict(report: FeasibilityReport) -> dict[str, object]:
    return asdict(report)


def report_to_json(report: FeasibilityReport) -> str:
    return json.dumps(report_to_dict(report), indent=2) + "\n"


def render_markdown(report: FeasibilityReport) -> str:
    """Human-readable rendering of the same facts.

    A migration decision gets made by someone who will not read JSON, and
    if the honest version is only machine-readable then the optimistic
    version is what reaches the decision.
    """
    totals = report.totals

    def pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    lines: list[str] = [
        f"# Feasibility scan -- {report.profile}",
        "",
        f"- Repository: `{report.repository}`",
        f"- Source dialect: `{report.source_dialect}`",
        f"- Scanned: {report.scanned_at}",
        "",
        "## Result",
        "",
        f"**{totals['inSubset']} of {totals['discovered']} statements are inside the certified "
        f"subset ({pct(report.upper_bound_coverage)}, upper bound), across {totals['files']} files.**",
        "",
        f"**Disposition coverage: {totals['dispositionCovered']} of {totals['dispositionUnits']} "
        f"discovered units ({pct(report.disposition_coverage)}).** Every unit has an explicit "
        "automatic-candidate, manual-migration, source-review, or engine-defect disposition.",
        "",
        "| | Count |",
        "|---|---|",
        f"| SQL files | {totals['files']} |",
        f"| Statements discovered | {totals['discovered']} |",
        f"| In subset (upper bound) | {totals['inSubset']} |",
        f"| Out of subset | {totals['outOfSubset']} |",
        f"| Scan errors (engine defects) | {totals['scanErrors']} |",
        f"| Disposition units | {totals['dispositionUnits']} |",
        f"| Disposition covered | {totals['dispositionCovered']} |",
        f"| Disposition unknown | {totals['dispositionUnknown']} |",
        "",
    ]

    china = report.chinadb_coverage
    if china:
        lines += [
            "## ChinaDB domestic target coverage",
            "",
            f"**{china['routeDispositionCovered']} of {china['routeUnits']} domestic target-route "
            f"units ({pct(cast(float, china['routeDispositionCoverage']))}) have an explicit disposition "
            "across 13 exact target identities.**",
            "",
            "This is complete route accounting, not a claim that every unit emits target SQL. "
            "The registry is `SPEC_ONLY`; unverified target adapters remain explicit review work.",
            "",
            "| | Count |",
            "|---|---|",
            f"| ChinaDB target identities | {china['targetCount']} |",
            f"| Planned source-family routes | {china['plannedRouteCount']} |",
            f"| Domestic route units | {china['routeUnits']} |",
            f"| Domestic route dispositions covered | {china['routeDispositionCovered']} |",
            f"| Domestic route dispositions unknown | {china['routeDispositionUnknown']} |",
            f"| Automatic target emissions | {china['automaticTargetEmissions']} |",
            "| External execution | `NOT_RUN` |",
            "| Certification | `NOT_CERTIFIED` |",
            "",
        ]

    if report.blockers:
        lines += [
            "## What is blocking, most frequent first",
            "",
            "`Distinct` is the number that should drive a roadmap: a high count with a low "
            "distinct value is one idiom copy-pasted across a schema, not many problems.",
            "",
            "| Blocker | Statements | Distinct | Share | What it is |",
            "|---|---|---|---|---|",
        ]
        for blocker in report.blockers:
            lines.append(
                f"| `{blocker.reason_code}` | {blocker.count} | {blocker.distinct_reasons} | "
                f"{pct(blocker.share_of_blocked)} | {blocker.what} |"
            )
        lines += ["", "### By family", "", "| Family | Statements | Share |", "|---|---|---|"]
        for family in report.families:
            lines.append(f"| {family.family} | {family.count} | {pct(family.share_of_blocked)} |")
        lines.append("")
        top = report.blockers[0]
        if len(report.blockers) > 1:
            lines += [
                f"Removing the single largest blocker (`{top.reason_code}`) would move at most "
                f'{top.count} statement(s) -- "at most" because a statement can be blocked by more '
                "than one construct and only the first one encountered is reported here.",
                "",
            ]

    lines += ["## Read this before deciding", ""]
    lines += [f"- {caveat}" for caveat in report.caveats]
    lines.append("")
    return "\n".join(lines)


def iter_statement_excerpts(findings: Iterable[ScanFinding]) -> list[str]:
    """Convenience for callers building their own summaries."""
    return [f.excerpt for f in findings]
