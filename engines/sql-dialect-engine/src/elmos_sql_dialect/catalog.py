"""A column-type catalogue, so index and constraint statements stop being blind.

`certified-ddl-v1` reads ONE statement at a time. That is the right unit for a
translation, but it makes two whole statement kinds undecidable against MySQL:

    CREATE INDEX ix ON t (c)
    ALTER TABLE t ADD CONSTRAINT u UNIQUE (c)

Neither carries `c`'s type, and MySQL refuses to index a TEXT-family column
without a prefix length (error 1170). Executing the corpus against a real
MySQL 8.0.46 showed 201 statements failing for exactly this reason, and the
engine could not have known -- so it emitted SQL the server rejected.

A catalogue closes that without weakening the one-statement rule: the caller
who HAS the surrounding schema (a repository scan, a migration run) builds one
and passes it in. Callers who genuinely have one statement and no context pass
nothing and get the previous behaviour, which is honest rather than silent --
`emit_*` cannot invent a type it was never given.

The catalogue is deliberately NOT read from a live database. This engine has no
connection in the translation path, and a catalogue that sometimes came from a
server and sometimes from the source files would make the same emission depend
on which. It is built from the source statements only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    AddColumn,
    AddConstraint,
    AlterTable,
    CanonicalType,
    DropColumn,
    RenameColumn,
    Table,
)


@dataclass
class ColumnCatalog:
    """Column canonical types, keyed by table then column.

    Names are folded to lower case: the certified subset admits only plain
    `[A-Za-z_][A-Za-z0-9_]*` identifiers, and the four dialects disagree about
    unquoted-identifier case folding, so a case-sensitive catalogue would miss
    `CREATE INDEX ... ON Orders (Id)` against `CREATE TABLE orders (id ...)`.
    """

    columns: dict[str, dict[str, CanonicalType]] = field(default_factory=dict)
    #: Declared primary key per table, lower-cased. MySQL requires the
    #: referenced column list on `ALTER TABLE ... ADD FOREIGN KEY`, where the
    #: other three dialects let it default to the target's primary key -- so
    #: the key has to be recoverable from somewhere, and this is the only
    #: place that has it without a database connection.
    primary_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def add_table(self, table: Table) -> None:
        entry = self.columns.setdefault(table.name.lower(), {})
        for column in table.columns:
            entry[column.name.lower()] = column.type_ref.canonical_type
        # The parser lifts an inline `c INT PRIMARY KEY` into `table.primary_key`,
        # so this one field covers both spellings.
        key = tuple(c.lower() for c in table.primary_key)
        if key:
            self.primary_keys[table.name.lower()] = key

    def apply_alter(self, alter: AlterTable) -> None:
        entry = self.columns.setdefault(alter.table.lower(), {})
        for action in alter.actions:
            if isinstance(action, AddColumn):
                entry[action.column.name.lower()] = action.column.type_ref.canonical_type
            elif isinstance(action, DropColumn):
                entry.pop(action.column.lower(), None)
            elif isinstance(action, RenameColumn):
                moved = entry.pop(action.column.lower(), None)
                if moved is not None:
                    entry[action.new_name.lower()] = moved
            elif isinstance(action, AddConstraint) and action.primary_key:
                # pg_dump-style schemas declare the primary key in a separate
                # ALTER, not in the CREATE TABLE. Missing this left the
                # catalogue with 9 tables and zero keys on northwind, which is
                # exactly the corpus where MySQL then demanded the referenced
                # column list it could no longer supply.
                self.primary_keys[alter.table.lower()] = tuple(
                    c.lower() for c in action.primary_key
                )

    def primary_key_of(self, table: str) -> tuple[str, ...] | None:
        """The table's declared primary key, or None when unknown.

        None means "the catalogue has not seen it", never "there is none".
        """
        return self.primary_keys.get(table.lower())

    def type_of(self, table: str, column: str) -> CanonicalType | None:
        """The column's canonical type, or None when the catalogue has not seen it.

        None means "unknown", never "fine". Every caller must treat it as the
        absence of evidence rather than as evidence of absence -- that
        distinction is the whole reason this returns an Optional instead of a
        default.
        """
        return self.columns.get(table.lower(), {}).get(column.lower())

    def known_columns(self, table: str, columns: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(c for c in columns if self.type_of(table, c) is not None)

    def columns_of_type(
        self, table: str, columns: tuple[str, ...], wanted: CanonicalType
    ) -> tuple[str, ...]:
        return tuple(c for c in columns if self.type_of(table, c) is wanted)

    def __bool__(self) -> bool:
        return bool(self.columns)
