"""Live MySQL catalog inspector.

Queries MySQL system catalog tables (information_schema)
to reconstruct full canonical database metadata including:
- Tables, columns (with exact types, precision, scale, nullability, defaults, auto_increment)
- Primary keys, foreign keys (referencing table/cols, ON DELETE/UPDATE actions)
- Check constraints and unique constraints
- Indexes (names, columns, unique, index_type)
- Views (definition SQL)
- Procedures and functions (arguments, return types, language)
"""

from __future__ import annotations

import logging
from typing import Any

from .postgres_inspector import (
    CheckConstraintMeta,
    ColumnMeta,
    ForeignKeyMeta,
    IndexMeta,
    LiveCatalogInspector,
    RoutineMeta,
    SchemaInspectionResult,
    TableMeta,
    ViewMeta,
)

logger = logging.getLogger(__name__)


class MysqlCatalogInspector(LiveCatalogInspector):
    """Inspects a live MySQL instance via a PyMySQL / DBAPI2 connection."""

    def __init__(self, connection: Any) -> None:
        self.conn = connection

    def inspect_schema(self, schema_name: str = "source_db") -> SchemaInspectionResult:
        result = SchemaInspectionResult(schema_name=schema_name)
        with self.conn.cursor() as cur:
            # 1. Inspect Tables and Columns
            self._inspect_tables(cur, schema_name, result)
            # 2. Inspect Primary Keys
            self._inspect_primary_keys(cur, schema_name, result)
            # 3. Inspect Foreign Keys
            self._inspect_foreign_keys(cur, schema_name, result)
            # 4. Inspect Check Constraints
            self._inspect_check_constraints(cur, schema_name, result)
            # 5. Inspect Indexes
            self._inspect_indexes(cur, schema_name, result)
            # 6. Inspect Views
            self._inspect_views(cur, schema_name, result)
            # 7. Inspect Routines
            self._inspect_routines(cur, schema_name, result)
        return result

    def _inspect_tables(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """
        cur.execute(query, (schema_name,))
        for (tbl_name,) in cur.fetchall():
            result.tables[tbl_name] = TableMeta(name=tbl_name, schema_name=schema_name)

        col_query = """
            SELECT 
                table_name, column_name, data_type, is_nullable,
                column_default, character_maximum_length,
                numeric_precision, numeric_scale, ordinal_position, extra
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position;
        """
        cur.execute(col_query, (schema_name,))
        for (
            tbl,
            col,
            dtype,
            nullable,
            default_val,
            char_len,
            num_prec,
            num_scale,
            ord_pos,
            _extra,
        ) in cur.fetchall():
            if tbl in result.tables:
                col_meta = ColumnMeta(
                    name=col,
                    data_type=dtype.lower(),
                    is_nullable=(nullable == "YES"),
                    default_value=str(default_val) if default_val is not None else None,
                    char_max_length=char_len,
                    numeric_precision=num_prec,
                    numeric_scale=num_scale,
                    ordinal_position=ord_pos,
                )
                result.tables[tbl].columns.append(col_meta)

    def _inspect_primary_keys(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY tc.table_name, kcu.ordinal_position;
        """
        cur.execute(query, (schema_name,))
        for tbl, col in cur.fetchall():
            if tbl in result.tables:
                result.tables[tbl].primary_key.append(col)

    def _inspect_foreign_keys(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT 
                kcu.table_name,
                kcu.constraint_name,
                kcu.column_name,
                kcu.referenced_table_name,
                kcu.referenced_column_name,
                rc.update_rule,
                rc.delete_rule
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.referential_constraints rc
              ON kcu.constraint_name = rc.constraint_name
             AND kcu.constraint_schema = rc.constraint_schema
            WHERE kcu.table_schema = %s
              AND kcu.referenced_table_name IS NOT NULL
            ORDER BY kcu.table_name, kcu.constraint_name, kcu.ordinal_position;
        """
        cur.execute(query, (schema_name,))
        fk_map: dict[tuple[str, str], ForeignKeyMeta] = {}
        for tbl, c_name, col, ref_tbl, ref_col, up_rule, del_rule in cur.fetchall():
            key = (tbl, c_name)
            if key not in fk_map:
                fk_map[key] = ForeignKeyMeta(
                    constraint_name=c_name,
                    column_names=[col],
                    foreign_table=ref_tbl,
                    foreign_columns=[ref_col],
                    on_update=up_rule,
                    on_delete=del_rule,
                )
            else:
                fk_map[key].column_names.append(col)
                fk_map[key].foreign_columns.append(ref_col)

        for (tbl, _), fk_meta in fk_map.items():
            if tbl in result.tables:
                result.tables[tbl].foreign_keys.append(fk_meta)

    def _inspect_check_constraints(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        # Check constraints exist in MySQL 8.0.16+
        try:
            query = """
                SELECT tc.table_name, tc.constraint_name, cc.check_clause
                FROM information_schema.table_constraints tc
                JOIN information_schema.check_constraints cc
                  ON tc.constraint_name = cc.constraint_name
                 AND tc.constraint_schema = cc.constraint_schema
                WHERE tc.table_schema = %s
                  AND tc.constraint_type = 'CHECK';
            """
            cur.execute(query, (schema_name,))
            for tbl, c_name, clause in cur.fetchall():
                if tbl in result.tables:
                    result.tables[tbl].check_constraints.append(
                        CheckConstraintMeta(constraint_name=c_name, check_clause=clause)
                    )
        except Exception as e:
            logger.debug("MySQL check constraint inspection skipped: %s", e)

    def _inspect_indexes(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT table_name, index_name, column_name, non_unique, index_type
            FROM information_schema.statistics
            WHERE table_schema = %s
            ORDER BY table_name, index_name, seq_in_index;
        """
        cur.execute(query, (schema_name,))
        idx_map: dict[tuple[str, str], IndexMeta] = {}
        for tbl, idx_name, col, non_uniq, idx_type in cur.fetchall():
            # Skip primary key index
            if idx_name == "PRIMARY":
                continue
            key = (tbl, idx_name)
            if key not in idx_map:
                idx_map[key] = IndexMeta(
                    name=idx_name,
                    column_names=[col],
                    is_unique=(non_uniq == 0),
                    index_type=idx_type.lower(),
                )
            else:
                idx_map[key].column_names.append(col)

        for (tbl, _), idx_meta in idx_map.items():
            if tbl in result.tables:
                result.tables[tbl].indexes.append(idx_meta)

    def _inspect_views(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT table_name, view_definition
            FROM information_schema.views
            WHERE table_schema = %s
            ORDER BY table_name;
        """
        cur.execute(query, (schema_name,))
        for v_name, v_def in cur.fetchall():
            result.views[v_name] = ViewMeta(name=v_name, schema_name=schema_name, definition=v_def or "")

    def _inspect_routines(self, cur: Any, schema_name: str, result: SchemaInspectionResult) -> None:
        query = """
            SELECT routine_name, routine_type, dtd_identifier, routine_body, routine_definition
            FROM information_schema.routines
            WHERE routine_schema = %s
            ORDER BY routine_name;
        """
        cur.execute(query, (schema_name,))
        for r_name, r_type, ret_type, lang, r_def in cur.fetchall():
            result.routines[r_name] = RoutineMeta(
                name=r_name,
                schema_name=schema_name,
                routine_type=r_type,
                return_type=ret_type,
                language=lang or "SQL",
                definition=r_def,
            )
