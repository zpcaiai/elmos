"""Live PostgreSQL catalog inspector.

Queries PostgreSQL system catalog tables (information_schema and pg_catalog)
to reconstruct full canonical database metadata including:
- Tables, columns (with exact types, precision, scale, nullability, defaults)
- Primary keys, foreign keys (referencing table/cols, ON DELETE/UPDATE actions)
- Check constraints and unique constraints
- Indexes (names, columns, unique, method)
- Views (definition SQL)
- Sequences (start, increment, min, max, cycle)
- Procedures and functions (arguments, return types, language)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    is_nullable: bool
    default_value: str | None = None
    char_max_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    ordinal_position: int = 0


@dataclass
class ForeignKeyMeta:
    constraint_name: str
    column_names: list[str]
    foreign_table: str
    foreign_columns: list[str]
    on_delete: str = "NO ACTION"
    on_update: str = "NO ACTION"


@dataclass
class CheckConstraintMeta:
    constraint_name: str
    check_clause: str


@dataclass
class IndexMeta:
    name: str
    column_names: list[str]
    is_unique: bool
    index_type: str = "btree"


@dataclass
class TableMeta:
    name: str
    schema_name: str
    columns: list[ColumnMeta] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKeyMeta] = field(default_factory=list)
    check_constraints: list[CheckConstraintMeta] = field(default_factory=list)
    indexes: list[IndexMeta] = field(default_factory=list)


@dataclass
class ViewMeta:
    name: str
    schema_name: str
    definition: str


@dataclass
class SequenceMeta:
    name: str
    schema_name: str
    data_type: str
    start_value: int
    increment: int
    min_value: int
    max_value: int
    cycle: bool


@dataclass
class RoutineMeta:
    name: str
    schema_name: str
    routine_type: str  # FUNCTION or PROCEDURE
    return_type: str | None
    language: str
    definition: str | None
    parameters: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SchemaInspectionResult:
    schema_name: str
    tables: dict[str, TableMeta] = field(default_factory=dict)
    views: dict[str, ViewMeta] = field(default_factory=dict)
    sequences: dict[str, SequenceMeta] = field(default_factory=dict)
    routines: dict[str, RoutineMeta] = field(default_factory=dict)


class LiveCatalogInspector:
    """Base interface for live database inspection."""

    def inspect_schema(self, schema_name: str = "public") -> SchemaInspectionResult:
        raise NotImplementedError


class PostgresCatalogInspector(LiveCatalogInspector):
    """Inspects a live PostgreSQL instance via a psycopg2 / psycopg connection."""

    def __init__(self, connection: Any) -> None:
        self.conn = connection

    def inspect_schema(self, schema_name: str = "public") -> SchemaInspectionResult:
        result = SchemaInspectionResult(schema_name=schema_name)
        with self.conn.cursor() as cur:
            # 1. Inspect Sequences
            self._inspect_sequences(cur, schema_name, result)
            # 2. Inspect Tables and Columns
            self._inspect_tables(cur, schema_name, result)
            # 3. Inspect Primary Keys
            self._inspect_primary_keys(cur, schema_name, result)
            # 4. Inspect Foreign Keys
            self._inspect_foreign_keys(cur, schema_name, result)
            # 5. Inspect Check Constraints
            self._inspect_check_constraints(cur, schema_name, result)
            # 6. Inspect Indexes
            self._inspect_indexes(cur, schema_name, result)
            # 7. Inspect Views
            self._inspect_views(cur, schema_name, result)
            # 8. Inspect Routines
            self._inspect_routines(cur, schema_name, result)
        return result

    def _inspect_sequences(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT sequence_name, data_type, start_value, increment, minimum_value, maximum_value, cycle_option
            FROM information_schema.sequences
            WHERE sequence_schema = %s
            ORDER BY sequence_name;
        """
        cur.execute(query, (schema_name,))
        for row in cur.fetchall():
            seq_name = row[0]
            result.sequences[seq_name] = SequenceMeta(
                name=seq_name,
                schema_name=schema_name,
                data_type=row[1] or "bigint",
                start_value=int(row[2] or 1),
                increment=int(row[3] or 1),
                min_value=int(row[4] or 1),
                max_value=int(row[5] or 9223372036854775807),
                cycle=(row[6] == "YES"),
            )

    def _inspect_tables(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        # Tables
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """,
            (schema_name,),
        )
        for (table_name,) in cur.fetchall():
            result.tables[table_name] = TableMeta(name=table_name, schema_name=schema_name)

        # Columns
        cur.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable, column_default,
                   character_maximum_length, numeric_precision, numeric_scale, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position;
            """,
            (schema_name,),
        )
        for row in cur.fetchall():
            tbl_name = row[0]
            if tbl_name in result.tables:
                col = ColumnMeta(
                    name=row[1],
                    data_type=row[2],
                    is_nullable=(row[3] == "YES"),
                    default_value=row[4],
                    char_max_length=row[5],
                    numeric_precision=row[6],
                    numeric_scale=row[7],
                    ordinal_position=row[8],
                )
                result.tables[tbl_name].columns.append(col)

    def _inspect_primary_keys(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s
            ORDER BY tc.table_name, kcu.ordinal_position;
        """
        cur.execute(query, (schema_name,))
        for tbl_name, col_name in cur.fetchall():
            if tbl_name in result.tables:
                result.tables[tbl_name].primary_key.append(col_name)

    def _inspect_foreign_keys(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT
                tc.table_name,
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                rc.delete_rule,
                rc.update_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints rc
              ON rc.constraint_name = tc.constraint_name
              AND rc.constraint_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
            ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
        """
        cur.execute(query, (schema_name,))
        fks: dict[tuple[str, str], ForeignKeyMeta] = {}
        for row in cur.fetchall():
            tbl_name, c_name, col_name, f_tbl, f_col, on_del, on_upd = row
            key = (tbl_name, c_name)
            if key not in fks:
                fks[key] = ForeignKeyMeta(
                    constraint_name=c_name,
                    column_names=[],
                    foreign_table=f_tbl,
                    foreign_columns=[],
                    on_delete=on_del,
                    on_update=on_upd,
                )
            fks[key].column_names.append(col_name)
            fks[key].foreign_columns.append(f_col)

        for (tbl_name, _), fk_meta in fks.items():
            if tbl_name in result.tables:
                result.tables[tbl_name].foreign_keys.append(fk_meta)

    def _inspect_check_constraints(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT tc.table_name, tc.constraint_name, cc.check_clause
            FROM information_schema.table_constraints tc
            JOIN information_schema.check_constraints cc
              ON tc.constraint_name = cc.constraint_name
              AND tc.constraint_schema = cc.constraint_schema
            WHERE tc.constraint_type = 'CHECK' AND tc.table_schema = %s
              AND tc.constraint_name NOT LIKE '%%_not_null'
            ORDER BY tc.table_name, tc.constraint_name;
        """
        cur.execute(query, (schema_name,))
        for tbl_name, c_name, clause in cur.fetchall():
            if tbl_name in result.tables:
                result.tables[tbl_name].check_constraints.append(
                    CheckConstraintMeta(constraint_name=c_name, check_clause=clause)
                )

    def _inspect_indexes(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT
                t.relname AS table_name,
                i.relname AS index_name,
                ix.indisunique AS is_unique,
                am.amname AS index_type,
                ARRAY_AGG(a.attname ORDER BY array_position(ix.indkey, a.attnum)) AS column_names
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_am am ON am.oid = i.relam
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE n.nspname = %s AND t.relkind = 'r' AND NOT ix.indisprimary
            GROUP BY t.relname, i.relname, ix.indisunique, am.amname
            ORDER BY t.relname, i.relname;
        """
        cur.execute(query, (schema_name,))
        for tbl_name, idx_name, is_uniq, idx_type, col_names in cur.fetchall():
            if tbl_name in result.tables:
                result.tables[tbl_name].indexes.append(
                    IndexMeta(
                        name=idx_name,
                        column_names=list(col_names),
                        is_unique=bool(is_uniq),
                        index_type=idx_type,
                    )
                )

    def _inspect_views(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT table_name, view_definition
            FROM information_schema.views
            WHERE table_schema = %s
            ORDER BY table_name;
        """
        cur.execute(query, (schema_name,))
        for v_name, v_def in cur.fetchall():
            result.views[v_name] = ViewMeta(
                name=v_name,
                schema_name=schema_name,
                definition=v_def or "",
            )

    def _inspect_routines(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT
                r.routine_name,
                r.routine_type,
                r.data_type,
                r.routine_body,
                r.routine_definition,
                p.prosrc
            FROM information_schema.routines r
            JOIN pg_namespace n ON n.nspname = r.routine_schema
            JOIN pg_proc p ON p.proname = r.routine_name AND p.pronamespace = n.oid
            WHERE r.routine_schema = %s
            ORDER BY r.routine_name;
        """
        try:
            cur.execute(query, (schema_name,))
            for r_name, r_type, ret_type, _, r_def, p_src in cur.fetchall():
                result.routines[r_name] = RoutineMeta(
                    name=r_name,
                    schema_name=schema_name,
                    routine_type=r_type,
                    return_type=ret_type,
                    language="plpgsql",
                    definition=p_src or r_def,
                )
        except Exception as exc:
            logger.warning("Failed to inspect routines: %s", exc)
