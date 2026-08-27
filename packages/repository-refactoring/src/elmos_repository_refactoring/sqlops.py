"""SQL parsing and expand-contract migration synthesis.

Deliberately dialect-aware in the places where dialects differ in ways that
break a migration:

* PostgreSQL supports ``CREATE INDEX CONCURRENTLY`` and cannot run it inside a
  transaction; MySQL does not have it at all.  Emitting the wrong one either
  locks a table for the duration or fails outright.
* ``ADD COLUMN ... DEFAULT`` rewrites the whole table on older engines.  The
  generated expand phase therefore adds the column nullable and backfills in
  batches rather than relying on a default.
* Dropping a column is irreversible.  It is emitted only in the contract
  phase, behind an explicit guard, and never in the same migration as the
  expand.

The statement splitter is a real lexer: it tracks single quotes, double quotes,
backticks, line and block comments and PostgreSQL dollar-quoting, so a
semicolon inside a string or a function body does not split a statement.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import ContractError, sha256_payload, sha256_text


class Dialect(StrEnum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    TSQL = "tsql"
    GENERIC = "generic"

    @property
    def supports_concurrent_index(self) -> bool:
        return self is Dialect.POSTGRESQL

    @property
    def transactional_ddl(self) -> bool:
        return self in (Dialect.POSTGRESQL, Dialect.SQLITE)


#: Statements that destroy data.  Their presence outside an approved contract
#: phase is a hard failure, not a warning.
DESTRUCTIVE = re.compile(
    r"(?i)\b(DROP\s+(?:TABLE|COLUMN|SCHEMA|DATABASE|INDEX)|TRUNCATE|DELETE\s+FROM(?!\s+\w+\s+WHERE))\b"
)

_CREATE_TABLE = re.compile(
    r"(?is)^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]]+)\s*\((.*)\)\s*;?\s*$"
)
_ALTER_TABLE = re.compile(r"(?is)^\s*ALTER\s+TABLE\s+([\w.\"`\[\]]+)\s+(.*?);?\s*$")
#: Multi-word SQL types, longest first.  A naive ``[A-Za-z][\w ]*`` type
#: pattern swallows the trailing ``NOT NULL`` and silently reports every column
#: as nullable — which is exactly the kind of wrong-but-plausible parse that
#: produces a migration nobody can run.
_MULTIWORD_TYPES = (
    r"TIMESTAMP\s+WITH(?:OUT)?\s+TIME\s+ZONE",
    r"TIME\s+WITH(?:OUT)?\s+TIME\s+ZONE",
    r"DOUBLE\s+PRECISION",
    r"CHARACTER\s+VARYING",
    r"CHARACTER\s+LARGE\s+OBJECT",
    r"BIT\s+VARYING",
    r"NATIONAL\s+CHARACTER(?:\s+VARYING)?",
)

_COLUMN = re.compile(
    r"(?ix)^\s*"
    r"(?P<name>[\w\"`\[\]]+)\s+"
    r"(?P<type>(?:" + "|".join(_MULTIWORD_TYPES) + r"|[A-Za-z][A-Za-z0-9_]*)"
    r"(?:\s*\([^)]*\))?"
    r"(?:\s+UNSIGNED)?"
    r"(?:\s*\[\s*\])*)"
    r"(?P<rest>.*)$"
)
_CONSTRAINT_START = re.compile(
    r"(?i)^\s*(CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|EXCLUDE|INDEX|KEY)\b"
)


def _strip_leading_comments(text: str) -> str:
    """Remove leading line and block comments from a statement."""

    cursor = 0
    length = len(text)
    while cursor < length:
        while cursor < length and text[cursor].isspace():
            cursor += 1
        if text.startswith("--", cursor):
            end = text.find("\n", cursor)
            cursor = length if end == -1 else end + 1
            continue
        if text.startswith("/*", cursor):
            end = text.find("*/", cursor + 2)
            cursor = length if end == -1 else end + 2
            continue
        break
    return text[cursor:]


@dataclass(frozen=True, slots=True)
class Statement:
    text: str
    index: int
    line: int

    @property
    def body(self) -> str:
        """The statement with leading comments removed.

        Comments are kept in :attr:`text` so the generated file stays lossless,
        but every parser has to see the statement itself — otherwise a leading
        ``-- note`` makes ``CREATE TABLE`` unrecognisable.
        """

        return _strip_leading_comments(self.text)

    @property
    def kind(self) -> str:
        head = self.body.lstrip().split(None, 2)
        if not head:
            return "empty"
        first = head[0].upper()
        second = head[1].upper() if len(head) > 1 else ""
        return f"{first} {second}".strip()

    @property
    def destructive(self) -> bool:
        # Search the body, so a destructive statement cannot be hidden behind a
        # comment and a comment mentioning DROP TABLE is not a false positive.
        return bool(DESTRUCTIVE.search(self.body))

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "line": self.line,
            "kind": self.kind,
            "destructive": self.destructive,
            "digest": sha256_text(self.text),
        }


def split_statements(sql: str) -> tuple[Statement, ...]:
    """Split on statement-terminating semicolons only."""

    statements: list[Statement] = []
    current: list[str] = []
    index = 0
    line = 1
    start_line = 1
    position = 0
    length = len(sql)
    while position < length:
        char = sql[position]
        if char == "\n":
            line += 1
        # line comment
        if sql.startswith("--", position):
            end = sql.find("\n", position)
            end = length if end == -1 else end
            current.append(sql[position:end])
            position = end
            continue
        # block comment
        if sql.startswith("/*", position):
            end = sql.find("*/", position + 2)
            end = length if end == -1 else end + 2
            segment = sql[position:end]
            line += segment.count("\n")
            current.append(segment)
            position = end
            continue
        # dollar quoting
        if char == "$":
            match = re.match(r"\$[A-Za-z_]*\$", sql[position:])
            if match:
                tag = match.group()
                end = sql.find(tag, position + len(tag))
                end = length if end == -1 else end + len(tag)
                segment = sql[position:end]
                line += segment.count("\n")
                current.append(segment)
                position = end
                continue
        if char in ("'", '"', "`"):
            closer = char
            cursor = position + 1
            while cursor < length:
                if sql[cursor] == "\\" and closer == "'":
                    cursor += 2
                    continue
                if sql[cursor] == closer:
                    if closer == "'" and cursor + 1 < length and sql[cursor + 1] == "'":
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            segment = sql[position:cursor]
            line += segment.count("\n")
            current.append(segment)
            position = cursor
            continue
        if char == ";":
            text = "".join(current).strip()
            if text:
                index += 1
                statements.append(Statement(text=text, index=index, line=start_line))
            current = []
            position += 1
            start_line = line
            continue
        current.append(char)
        position += 1
    tail = "".join(current).strip()
    if tail:
        index += 1
        statements.append(Statement(text=tail, index=index, line=start_line))
    return tuple(statements)


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "nullable": self.nullable,
            "default": self.default,
            "primaryKey": self.primary_key,
        }


@dataclass(frozen=True, slots=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    constraints: tuple[str, ...] = ()

    def column(self, name: str) -> Column | None:
        for item in self.columns:
            if item.name.lower() == name.lower():
                return item
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "columns": [item.to_payload() for item in self.columns],
            "constraints": list(self.constraints),
        }


def _unquote(name: str) -> str:
    return name.strip().strip('"`[]')


def _split_definitions(body: str) -> Iterator[str]:
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            yield "".join(current)
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        yield "".join(current)


def _parse_column(definition: str) -> Column | None:
    """Parse one column definition, or ``None`` when it is a constraint."""

    cleaned = definition.strip().rstrip(";")
    if not cleaned or _CONSTRAINT_START.match(cleaned):
        return None
    match = _COLUMN.match(cleaned)
    if not match:
        return None
    rest = match.group("rest") or ""
    default_match = re.search(
        r"(?i)\bDEFAULT\s+(.+?)"
        r"(?:\s+(?:NOT\s+NULL|NULL|PRIMARY|UNIQUE|CHECK|REFERENCES|GENERATED)\b|$)",
        rest,
    )
    lowered = rest.lower()
    return Column(
        name=_unquote(match.group("name")),
        type=match.group("type").strip(),
        nullable="not null" not in lowered and "primary key" not in lowered,
        default=default_match.group(1).strip() if default_match else None,
        primary_key="primary key" in lowered,
    )


def parse_schema(sql: str) -> tuple[Table, ...]:
    """Parse ``CREATE TABLE`` statements and apply ``ALTER TABLE ADD COLUMN``."""

    tables: dict[str, Table] = {}
    for statement in split_statements(sql):
        create = _CREATE_TABLE.match(statement.body)
        if create:
            name = _unquote(create.group(1))
            columns: list[Column] = []
            constraints: list[str] = []
            for definition in _split_definitions(create.group(2)):
                cleaned = definition.strip()
                if not cleaned:
                    continue
                column = _parse_column(cleaned)
                if column is None:
                    constraints.append(cleaned)
                    continue
                columns.append(column)
            tables[name] = Table(name=name, columns=tuple(columns), constraints=tuple(constraints))
            continue
        alter = _ALTER_TABLE.match(statement.body)
        if alter:
            name = _unquote(alter.group(1))
            action = alter.group(2)
            add = re.match(r"(?i)^ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(.*)$", action, re.DOTALL)
            existing = tables.get(name)
            if add and existing is not None:
                # Reuse the same column parser as CREATE TABLE so an added
                # column is not parsed by weaker rules than a declared one.
                column = _parse_column(add.group(1))
                if column is not None:
                    tables[name] = Table(
                        name=name,
                        columns=(*existing.columns, column),
                        constraints=existing.constraints,
                    )
    return tuple(tables[key] for key in sorted(tables))


# ---------------------------------------------------------------------------
# Expand / backfill / contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MigrationFile:
    filename: str
    phase: str
    sql: str
    transactional: bool = True
    online_safe: bool = True
    notes: tuple[str, ...] = ()

    @property
    def destructive(self) -> bool:
        return any(item.destructive for item in split_statements(self.sql))

    def to_payload(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "phase": self.phase,
            "transactional": self.transactional,
            "onlineSafe": self.online_safe,
            "destructive": self.destructive,
            "digest": sha256_text(self.sql),
            "notes": list(self.notes),
            "sql": self.sql,
        }


@dataclass(frozen=True, slots=True)
class BackfillWorkflow:
    table: str
    source_column: str
    target_column: str
    key_column: str
    batch_size: int
    watermark_table: str
    sql: str
    checksum_sql: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "sourceColumn": self.source_column,
            "targetColumn": self.target_column,
            "keyColumn": self.key_column,
            "batchSize": self.batch_size,
            "watermarkTable": self.watermark_table,
            "resumable": True,
            "idempotent": True,
            "sql": self.sql,
            "checksumSql": self.checksum_sql,
        }


@dataclass(frozen=True, slots=True)
class SchemaMigrationPlan:
    table: str
    strategy: str
    files: tuple[MigrationFile, ...]
    backfill: BackfillWorkflow | None
    validations: tuple[str, ...]
    rollback: tuple[str, ...]
    blocked_reason: str = ""
    dialect: Dialect = Dialect.POSTGRESQL

    @property
    def phases(self) -> tuple[str, ...]:
        return tuple(item.phase for item in self.files)

    @property
    def executable(self) -> bool:
        return not self.blocked_reason

    def to_payload(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "strategy": self.strategy,
            "dialect": self.dialect.value,
            "phases": list(self.phases),
            "files": [item.to_payload() for item in self.files],
            "backfill": None if self.backfill is None else self.backfill.to_payload(),
            "validations": list(self.validations),
            "rollback": list(self.rollback),
            "executable": self.executable,
            "blockedReason": self.blocked_reason,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")


def require_sql_identifier(value: str, field_name: str) -> str:
    """Validate an identifier before it is interpolated into generated SQL.

    The generated migrations are text artifacts, not executed queries, but a
    table or column name that arrives from a Recipe parameter still has to be
    an identifier — otherwise a crafted parameter writes arbitrary SQL into a
    file somebody will run.
    """

    text = str(value).strip()
    if not _SQL_IDENTIFIER.match(text):
        raise ContractError(
            "invalid_sql_identifier",
            f"{field_name} must be a plain SQL identifier, optionally schema-qualified",
            {"value": text[:120]},
        )
    return text


def plan_column_rename(
    table: Table,
    *,
    old_column: str,
    new_column: str,
    key_column: str = "id",
    dialect: Dialect = Dialect.POSTGRESQL,
    batch_size: int = 5000,
    strategy: str = "expand-contract",
) -> SchemaMigrationPlan:
    """Generate an online-safe expand / backfill / contract column rename."""

    require_sql_identifier(table.name, "table.name")
    old_column = require_sql_identifier(old_column, "old_column")
    new_column = require_sql_identifier(new_column, "new_column")
    key_column = require_sql_identifier(key_column, "key_column")
    source = table.column(old_column)
    if source is None:
        return SchemaMigrationPlan(
            table=table.name,
            strategy=strategy,
            files=(),
            backfill=None,
            validations=(),
            rollback=(),
            blocked_reason=f"column '{old_column}' does not exist on '{table.name}'",
            dialect=dialect,
        )
    if table.column(new_column) is not None:
        return SchemaMigrationPlan(
            table=table.name,
            strategy=strategy,
            files=(),
            backfill=None,
            validations=(),
            rollback=(),
            blocked_reason=f"column '{new_column}' already exists on '{table.name}'",
            dialect=dialect,
        )
    if strategy == "approved-destructive":
        return _destructive_plan(table, old_column, new_column, dialect)

    watermark = f"{table.name.replace('.', '_')}_backfill_watermark"
    index_sql = (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {table.name.split('.')[-1]}_{new_column}_idx "
        f"ON {table.name} ({new_column});"
        if dialect.supports_concurrent_index
        else f"CREATE INDEX {table.name.split('.')[-1]}_{new_column}_idx ON {table.name} ({new_column});"
    )

    expand = MigrationFile(
        filename="001_expand.sql",
        phase="expand",
        sql=(
            f"-- expand: additive only, no rewrite, no lock beyond a catalogue update\n"
            f"ALTER TABLE {table.name} ADD COLUMN {new_column} {source.type};\n"
        ),
        transactional=dialect.transactional_ddl,
        online_safe=True,
        notes=(
            "the column is added nullable and without a default: a default would rewrite "
            "the whole table on several engines",
        ),
    )
    index_file = MigrationFile(
        filename="002_index.sql",
        phase="expand",
        sql=f"-- expand: index the new column before it carries reads\n{index_sql}\n",
        transactional=not dialect.supports_concurrent_index,
        online_safe=True,
        notes=(
            "CREATE INDEX CONCURRENTLY cannot run inside a transaction block"
            if dialect.supports_concurrent_index
            else "this dialect has no concurrent index build; schedule a maintenance window for large tables",
        ),
    )
    backfill_sql = (
        f"-- backfill: batched, resumable and idempotent\n"
        f"WITH batch AS (\n"
        f"    SELECT {key_column}\n"
        f"    FROM {table.name}\n"
        f"    WHERE {new_column} IS DISTINCT FROM {old_column}\n"
        f"      AND {key_column} > :watermark\n"
        f"    ORDER BY {key_column}\n"
        f"    LIMIT {batch_size}\n"
        f")\n"
        f"UPDATE {table.name} AS t\n"
        f"SET {new_column} = t.{old_column}\n"
        f"FROM batch\n"
        f"WHERE t.{key_column} = batch.{key_column}\n"
        f"RETURNING t.{key_column};\n"
    )
    backfill = BackfillWorkflow(
        table=table.name,
        source_column=old_column,
        target_column=new_column,
        key_column=key_column,
        batch_size=batch_size,
        watermark_table=watermark,
        sql=backfill_sql,
        checksum_sql=(
            f"SELECT count(*) AS total,\n"
            f"       count(*) FILTER (WHERE {new_column} IS DISTINCT FROM {old_column}) AS mismatched,\n"
            f"       md5(string_agg({new_column}::text, ',' ORDER BY {key_column})) AS digest\n"
            f"FROM {table.name};\n"
        ),
    )
    backfill_file = MigrationFile(
        filename="003_backfill.sql",
        phase="backfill",
        sql=backfill_sql,
        transactional=True,
        online_safe=True,
        notes=(
            f"run repeatedly until zero rows are returned; the watermark lives in {watermark}",
            "the WHERE clause makes a re-run a no-op, so an interrupted backfill resumes safely",
        ),
    )
    contract = MigrationFile(
        filename="004_contract.sql",
        phase="contract",
        sql=(
            f"-- contract: DESTRUCTIVE. Do not run until old-path usage is zero and approved.\n"
            f"-- guard: SELECT count(*) FROM {table.name} WHERE {new_column} IS DISTINCT FROM {old_column};\n"
            f"--        must return 0 before this file runs.\n"
            f"ALTER TABLE {table.name} DROP COLUMN {old_column};\n"
        ),
        transactional=dialect.transactional_ddl,
        online_safe=False,
        notes=(
            "dropping a column is irreversible; the rollback path for this phase is a restore, not a migration",
        ),
    )
    return SchemaMigrationPlan(
        table=table.name,
        strategy=strategy,
        files=(expand, index_file, backfill_file, contract),
        backfill=backfill,
        validations=(
            f"row count is unchanged across every phase on {table.name}",
            f"zero rows where {new_column} IS DISTINCT FROM {old_column} before contract",
            "checksum over the new column matches the checksum over the old column",
            "application deploys reading the new column precede the contract phase",
            "old-path usage telemetry reads zero for a full release window",
        ),
        rollback=(
            "expand: drop the added column (no data has been written through it yet)",
            "backfill: stop the worker; the added column is additive so nothing needs undoing",
            "contract: NOT reversible by migration — restore from backup; this is why it is gated",
        ),
        dialect=dialect,
    )


def _destructive_plan(table: Table, old_column: str, new_column: str, dialect: Dialect) -> SchemaMigrationPlan:
    return SchemaMigrationPlan(
        table=table.name,
        strategy="approved-destructive",
        files=(
            MigrationFile(
                filename="001_rename.sql",
                phase="contract",
                sql=(
                    f"-- DESTRUCTIVE single-step rename. Requires an approved maintenance window.\n"
                    f"ALTER TABLE {table.name} RENAME COLUMN {old_column} TO {new_column};\n"
                ),
                transactional=dialect.transactional_ddl,
                online_safe=False,
                notes=(
                    "every reader and writer must be deployed simultaneously; there is no compatibility window",
                ),
            ),
        ),
        backfill=None,
        validations=("all application instances are deployed before the rename",),
        rollback=(f"ALTER TABLE {table.name} RENAME COLUMN {new_column} TO {old_column};",),
        dialect=dialect,
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PhaseOrderReport:
    ordered: bool
    violations: tuple[str, ...]
    destructive_outside_contract: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "ordered": self.ordered,
            "violations": list(self.violations),
            "destructiveOutsideContract": list(self.destructive_outside_contract),
        }


_PHASE_ORDER = ("expand", "backfill", "verify", "contract")


def check_phase_order(files: Sequence[MigrationFile]) -> PhaseOrderReport:
    """Expand must precede backfill, which must precede contract."""

    violations: list[str] = []
    destructive: list[str] = []
    highest = -1
    for item in files:
        if item.phase not in _PHASE_ORDER:
            violations.append(f"{item.filename}: unknown phase '{item.phase}'")
            continue
        position = _PHASE_ORDER.index(item.phase)
        if position < highest:
            violations.append(
                f"{item.filename}: phase '{item.phase}' appears after a later phase"
            )
        highest = max(highest, position)
        if item.destructive and item.phase != "contract":
            destructive.append(f"{item.filename}: destructive statement in phase '{item.phase}'")
    return PhaseOrderReport(
        ordered=not violations and not destructive,
        violations=tuple(violations),
        destructive_outside_contract=tuple(destructive),
    )


@dataclass(frozen=True, slots=True)
class DataValidation:
    name: str
    sql: str
    expected: str

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "sql": self.sql, "expected": self.expected}


def validation_queries(plan: SchemaMigrationPlan) -> tuple[DataValidation, ...]:
    if plan.backfill is None:
        return ()
    backfill = plan.backfill
    return (
        DataValidation(
            "row-count-unchanged",
            f"SELECT count(*) FROM {backfill.table};",
            "equal to the pre-migration count",
        ),
        DataValidation(
            "backfill-complete",
            f"SELECT count(*) FROM {backfill.table} "
            f"WHERE {backfill.target_column} IS DISTINCT FROM {backfill.source_column};",
            "0",
        ),
        DataValidation("checksum-match", backfill.checksum_sql, "mismatched = 0"),
        DataValidation(
            "sample-inspection",
            f"SELECT {backfill.key_column}, {backfill.source_column}, {backfill.target_column} "
            f"FROM {backfill.table} ORDER BY random() LIMIT 100;",
            "every sampled row matches",
        ),
    )


def find_destructive(sql: str) -> tuple[Statement, ...]:
    return tuple(item for item in split_statements(sql) if item.destructive)


def require_expand_contract(sql: str, *, strategy: str) -> None:
    """Refuse a destructive migration unless the strategy explicitly allows it."""

    destructive = find_destructive(sql)
    if destructive and strategy not in ("approved-destructive", "maintenance-window"):
        raise ContractError(
            "destructive_migration_forbidden",
            f"{len(destructive)} destructive statement(s) under strategy '{strategy}'; "
            "use expand-contract or obtain an explicit exception",
            {"statements": [item.kind for item in destructive]},
        )


def data_access_paths(files: Mapping[str, str]) -> tuple[str, ...]:
    """Files that read or write a schema — ORM models, queries and migrations."""

    found: list[str] = []
    for path, text in sorted(files.items()):
        lowered = text.lower()
        if any(
            marker in lowered
            for marker in ("select ", "insert into", "update ", "create table", "__tablename__", "@entity")
        ):
            found.append(path)
    return tuple(found)


__all__ = [
    "DESTRUCTIVE",
    "BackfillWorkflow",
    "Column",
    "DataValidation",
    "Dialect",
    "MigrationFile",
    "PhaseOrderReport",
    "SchemaMigrationPlan",
    "Statement",
    "Table",
    "check_phase_order",
    "data_access_paths",
    "find_destructive",
    "parse_schema",
    "plan_column_rename",
    "require_expand_contract",
    "require_sql_identifier",
    "split_statements",
    "validation_queries",
]
