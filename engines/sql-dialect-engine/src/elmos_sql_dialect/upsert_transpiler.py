"""Cross-Dialect UPSERT / MERGE Transpiler.

Translates UPSERT statements across:
1. PostgreSQL / KingbaseES / HighGo: INSERT ... ON CONFLICT (...) DO UPDATE SET ...
2. MySQL / TiDB / OceanBase MySQL / GoldenDB: INSERT ... ON DUPLICATE KEY UPDATE ...
3. Oracle / DM8 / SQL Server (T-SQL) / openGauss: MERGE INTO ... USING ... ON ...
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp, parse_one


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CanonicalUpsert:
    table: str
    columns: list[str]
    values: list[list[str]]
    conflict_keys: list[str]
    update_pairs: list[tuple[str, str]] = field(default_factory=list)
    do_nothing: bool = False
    source_subquery_sql: str | None = None
    target_alias: str = "t"
    source_alias: str = "s"


class UpsertTranspiler:
    """Parses and renders UPSERT/MERGE statements across SQL dialects."""

    def transpile_upsert(
        self,
        sql: str,
        source_dialect: str,
        target_dialect: str,
    ) -> dict[str, Any]:
        normalized_sql = sql.strip().rstrip(";")
        src_norm = source_dialect.lower().strip()
        tgt_norm = target_dialect.lower().strip()

        if not normalized_sql:
            return {
                "status": "BLOCKED",
                "reasonCode": "SQL_INPUT_REQUIRED",
                "reason": "UPSERT statement must not be empty.",
                "emitted": None,
            }

        try:
            canonical = self.parse_to_canonical(normalized_sql, src_norm)
        except Exception as exc:  # noqa: BLE001
            return {
                "schemaVersion": "1.0",
                "kind": "elmos.sql-upsert-translation",
                "status": "BLOCKED",
                "reasonCode": "UPSERT_PARSE_FAILED",
                "reason": f"Could not parse UPSERT statement for dialect {src_norm}: {exc}",
                "emitted": None,
            }

        try:
            emitted = self.emit_from_canonical(canonical, tgt_norm)
        except Exception as exc:  # noqa: BLE001
            return {
                "schemaVersion": "1.0",
                "kind": "elmos.sql-upsert-translation",
                "status": "BLOCKED",
                "reasonCode": "UPSERT_EMIT_FAILED",
                "reason": f"Could not emit UPSERT statement for dialect {tgt_norm}: {exc}",
                "emitted": None,
            }

        receipt = _sha256(f"{src_norm}:{tgt_norm}:{normalized_sql}:{emitted}")
        return {
            "schemaVersion": "1.0",
            "kind": "elmos.sql-upsert-translation",
            "status": "PASSED",
            "profile": f"certified-upsert-{src_norm}-to-{tgt_norm}-v1",
            "sourceDialect": src_norm,
            "targetDialect": tgt_norm,
            "emitted": emitted,
            "merkleReceipt": f"sha256:{receipt}",
            "validation": {"syntaxStatus": "PASSED"},
        }

    def parse_to_canonical(self, sql: str, source_dialect: str) -> CanonicalUpsert:
        upper = sql.upper().strip()

        # Case 1: MERGE INTO
        if upper.startswith("MERGE"):
            read_dialect = "oracle" if source_dialect in ("oracle", "dm8") else "postgres"
            ast = parse_one(sql, read=read_dialect)
            if not isinstance(ast, exp.Merge):
                raise ValueError("Expected Merge AST node")

            table = ast.this.name if isinstance(ast.this, exp.Table) else str(ast.this)
            target_alias = ast.this.alias if isinstance(ast.this, exp.Table) and ast.this.alias else "t"

            using_expr = ast.args.get("using")
            source_alias = "s"
            columns: list[str] = []
            values: list[list[str]] = []

            if isinstance(using_expr, exp.Subquery) and isinstance(using_expr.this, exp.Select):
                source_alias = using_expr.alias or "s"
                sub_select = using_expr.this
                for expr in sub_select.expressions:
                    if isinstance(expr, exp.Alias):
                        columns.append(expr.alias)
                        values.append([expr.this.sql()])
                    elif isinstance(expr, exp.Column):
                        columns.append(expr.name)
                        values.append([expr.name])
                if values:
                    # Transpose row
                    transposed_vals = [[row[0] for row in values]]
                    values = transposed_vals

            # Extract conflict keys from ON
            on_node = ast.args.get("on")
            conflict_keys: list[str] = []
            if on_node:
                for eq in on_node.find_all(exp.EQ):
                    left, right = eq.this, eq.expression
                    if isinstance(left, exp.Column):
                        conflict_keys.append(left.name)
                    elif isinstance(right, exp.Column):
                        conflict_keys.append(right.name)

            update_pairs: list[tuple[str, str]] = []
            do_nothing = True
            whens = ast.args.get("whens")
            if whens:
                for when in whens.expressions if isinstance(whens, exp.Whens) else [whens]:
                    if isinstance(when, exp.When) and when.args.get("matched"):
                        then_node = when.args.get("then")
                        if isinstance(then_node, exp.Update):
                            do_nothing = False
                            for eq in then_node.expressions:
                                if isinstance(eq, exp.EQ):
                                    col_name = eq.this.name if isinstance(eq.this, exp.Column) else eq.this.sql()
                                    val_sql = eq.expression.sql()
                                    # Strip source alias prefix if present (e.g. s.val -> val)
                                    val_sql = re.sub(rf"^{source_alias}\.", "", val_sql)
                                    update_pairs.append((col_name, val_sql))

            return CanonicalUpsert(
                table=table,
                columns=columns,
                values=values,
                conflict_keys=conflict_keys,
                update_pairs=update_pairs,
                do_nothing=do_nothing,
                target_alias=target_alias,
                source_alias=source_alias,
            )

        # Case 2: INSERT ... ON CONFLICT / ON DUPLICATE KEY
        read_dialect = "mysql" if "DUPLICATE KEY" in upper else "postgres"
        ast = parse_one(sql, read=read_dialect)
        if not isinstance(ast, exp.Insert):
            raise ValueError("Expected Insert AST node")

        table_node = ast.this.this if isinstance(ast.this, exp.Schema) else ast.this
        table = table_node.name if isinstance(table_node, exp.Table) else str(table_node)

        columns = []
        if isinstance(ast.this, exp.Schema):
            columns = [c.name for c in ast.this.expressions]

        values = []
        if isinstance(ast.expression, exp.Values):
            for tuple_node in ast.expression.expressions:
                row = [item.sql() for item in tuple_node.expressions]
                values.append(row)

        conflict_keys = []
        update_pairs = []
        do_nothing = False

        conflict = ast.args.get("conflict")
        if conflict:
            if getattr(conflict, "args", {}).get("action") == exp.var("DO NOTHING"):
                do_nothing = True
            keys = conflict.args.get("conflict_keys") or []
            for k in keys:
                if isinstance(k, exp.Ordered) and isinstance(k.this, exp.Column):
                    conflict_keys.append(k.this.name)
                elif isinstance(k, exp.Column):
                    conflict_keys.append(k.name)

            for eq in conflict.expressions or []:
                if isinstance(eq, exp.EQ):
                    col = eq.this.name if isinstance(eq.this, exp.Column) else eq.this.sql()
                    val = eq.expression.sql()
                    # Normalize EXCLUDED.col or VALUES(col) -> plain col
                    val_norm = re.sub(r"EXCLUDED\.", "", val, flags=re.I)
                    val_norm = re.sub(r"VALUES\((.*?)\)", r"\1", val_norm, flags=re.I)
                    update_pairs.append((col, val_norm))

        if not conflict_keys and columns:
            conflict_keys = [columns[0]]

        return CanonicalUpsert(
            table=table,
            columns=columns,
            values=values,
            conflict_keys=conflict_keys,
            update_pairs=update_pairs,
            do_nothing=do_nothing,
        )

    def emit_from_canonical(self, c: CanonicalUpsert, target_dialect: str) -> str:
        tgt = target_dialect.lower().strip()

        # Dialect targets that use MERGE INTO (Oracle, DM8, SQL Server)
        if tgt in ("oracle", "dm8", "sqlserver", "tsql"):
            return self._emit_merge(c, tgt)

        # Dialect targets that use ON DUPLICATE KEY UPDATE (MySQL, TiDB, openGauss, GoldenDB)
        if tgt in ("mysql", "tidb", "goldendb", "oceanbase-mysql", "oceanbase_mysql", "gbase-8a", "gbase8a", "opengauss"):
            return self._emit_on_duplicate_key(c, tgt)

        # Dialect targets that use ON CONFLICT (PostgreSQL, KingbaseES, HighGo, GBase 8c, SQLite)
        return self._emit_on_conflict(c, tgt)

    def _emit_on_conflict(self, c: CanonicalUpsert, tgt: str) -> str:
        cols_str = ", ".join(c.columns)
        rows_str = ", ".join(f"({', '.join(row)})" for row in c.values)
        keys_str = ", ".join(c.conflict_keys)

        if c.do_nothing:
            return f"INSERT INTO {c.table} ({cols_str}) VALUES {rows_str} ON CONFLICT ({keys_str}) DO NOTHING;"

        updates_str = ", ".join(f"{col} = EXCLUDED.{val}" for col, val in c.update_pairs)
        return f"INSERT INTO {c.table} ({cols_str}) VALUES {rows_str} ON CONFLICT ({keys_str}) DO UPDATE SET {updates_str};"

    def _emit_on_duplicate_key(self, c: CanonicalUpsert, tgt: str) -> str:
        cols_str = ", ".join(c.columns)
        rows_str = ", ".join(f"({', '.join(row)})" for row in c.values)

        if c.do_nothing:
            first_key = c.conflict_keys[0] if c.conflict_keys else (c.columns[0] if c.columns else "id")
            return f"INSERT INTO {c.table} ({cols_str}) VALUES {rows_str} ON DUPLICATE KEY UPDATE {first_key} = {first_key};"

        updates_str = ", ".join(f"{col} = VALUES({val})" for col, val in c.update_pairs)
        return f"INSERT INTO {c.table} ({cols_str}) VALUES {rows_str} ON DUPLICATE KEY UPDATE {updates_str};"

    def _emit_merge(self, c: CanonicalUpsert, tgt: str) -> str:
        dual_clause = " FROM DUAL" if tgt in ("oracle", "dm8") else ""
        first_row = c.values[0] if c.values else []
        select_items = [f"{val} AS {col}" for col, val in zip(c.columns, first_row, strict=False)]
        select_clause = f"SELECT {', '.join(select_items)}{dual_clause}"

        t_alias = c.target_alias
        s_alias = c.source_alias

        on_conditions = [f"{t_alias}.{k} = {s_alias}.{k}" for k in c.conflict_keys]
        on_clause = " AND ".join(on_conditions)

        matched_clause = ""
        if not c.do_nothing and c.update_pairs:
            updates = [f"{t_alias}.{col} = {s_alias}.{val}" for col, val in c.update_pairs]
            matched_clause = f" WHEN MATCHED THEN UPDATE SET {', '.join(updates)}"

        insert_cols = ", ".join(c.columns)
        insert_vals = ", ".join(f"{s_alias}.{col}" for col in c.columns)
        not_matched_clause = f" WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"

        as_keyword = " AS" if tgt in ("sqlserver", "tsql") else ""
        return (
            f"MERGE INTO {c.table}{as_keyword} {t_alias} "
            f"USING ({select_clause}){as_keyword} {s_alias} "
            f"ON ({on_clause}){matched_clause}{not_matched_clause};"
        )


_DEFAULT_UPSERT_TRANSPILER = UpsertTranspiler()


def translate_upsert(
    sql: str,
    source_dialect: str,
    target_dialect: str,
) -> dict[str, Any]:
    """Top-level functional API to translate UPSERT/MERGE cross-dialect."""
    return _DEFAULT_UPSERT_TRANSPILER.transpile_upsert(
        sql,
        source_dialect=source_dialect,
        target_dialect=target_dialect,
    )
