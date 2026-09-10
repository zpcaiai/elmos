"""GBase 8c (Distributed openGauss-based) Dedicated Target Lowerer.

GBase 8c provides distributed transactional processing, sharding distribution keys,
and openGauss-compatible procedural capabilities.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GBase8cTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GBase 8c."""

    target_id = "gbase8c"
    display_name = "GBase 8c"
    family = "pg_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to GBase 8c
            "VARCHAR2": "VARCHAR",
            "NVARCHAR2": "VARCHAR",
            "NUMBER": "NUMERIC",
            "BINARY_DOUBLE": "DOUBLE PRECISION",
            "BINARY_FLOAT": "REAL",
            "RAW": "BYTEA",
            "LONG RAW": "BYTEA",
            "LONG": "TEXT",
            "CLOB": "TEXT",
            "NCLOB": "TEXT",
            "BLOB": "BYTEA",
            # T-SQL to GBase 8c
            "DATETIME2": "TIMESTAMP",
            "SMALLDATETIME": "TIMESTAMP",
            "NVARCHAR(MAX)": "TEXT",
            "VARCHAR(MAX)": "TEXT",
            "VARBINARY(MAX)": "BYTEA",
            "IMAGE": "BYTEA",
            "MONEY": "NUMERIC(19, 4)",
            "SMALLMONEY": "NUMERIC(10, 4)",
            "BIT": "BOOLEAN",
            "UNIQUEIDENTIFIER": "UUID",
            # MySQL to GBase 8c
            "DATETIME": "TIMESTAMP",
            "LONGTEXT": "TEXT",
            "MEDIUMTEXT": "TEXT",
            "LONGBLOB": "BYTEA",
            "TINYINT": "SMALLINT",
            "ENUM": "VARCHAR(64)",
            "SET": "VARCHAR(256)",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            "NVL": "COALESCE",
            "ISNULL": "COALESCE",
            "IFNULL": "COALESCE",
            "GETDATE": "CURRENT_TIMESTAMP",
            "GETUTCDATE": "TIMEZONE('UTC', CURRENT_TIMESTAMP)",
            "SYSDATE": "CURRENT_TIMESTAMP",
            "NOW": "CURRENT_TIMESTAMP",
            "LEN": "LENGTH",
            "CHAR_LENGTH": "LENGTH",
            "INSTR": "INSTR",
            "CHARINDEX": "INSTR",
            "NEWID": "MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)::UUID",
            "SYS_GUID": "REPLACE(MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT), '-', '')",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="gbase8c_dual_removal",
                description="Remove FROM DUAL in queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gbase8c_square_brackets",
                description="Convert brackets [col] to GBase 8c \"col\"",
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="gbase8c_variable_prefix",
                description="Convert T-SQL @var to v_var",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="gb8c_replication_table",
                description="Small lookup tables can be marked DISTRIBUTE BY REPLICATION",
                pattern=r"/\*\s*DISTRIBUTE_REPLICATION\s*\*/",
                replacement="DISTRIBUTE BY REPLICATION",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Translate legacy DBMS error codes to GBase 8c / PG SQLSTATE."""
        return {
            "ORA-00001": "23505",
            "ORA-00942": "42P01",
            "ORA-00904": "42703",
            "ORA-01400": "23502",
            "ORA-01403": "P0002",
            "ORA-02291": "23503",
            "ORA-02292": "23503",
            "1062": "23505",
            "1146": "42P01",
            "2627": "23505",
        }

    def _build_catalog_queries(self) -> dict[str, str]:
        """GBase 8c distributed catalog queries."""
        return {
            "tables": (
                "SELECT tablename AS table_name FROM pg_tables "
                "WHERE schemaname = current_schema() ORDER BY tablename"
            ),
            "columns": (
                "SELECT column_name, data_type, character_maximum_length, "
                "is_nullable FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :tab_name "
                "ORDER BY ordinal_position"
            ),
            "indexes": (
                "SELECT indexname AS index_name, tablename AS table_name "
                "FROM pg_indexes WHERE schemaname = current_schema() "
                "AND tablename = :tab_name"
            ),
            "constraints": (
                "SELECT conname AS constraint_name, contype AS constraint_type "
                "FROM pg_constraint "
                "WHERE connamespace = "
                "(SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
            ),
            "procedures": (
                "SELECT proname AS routine_name FROM pg_proc "
                "WHERE pronamespace = "
                "(SELECT oid FROM pg_namespace WHERE nspname = current_schema())"
            ),
        }

    def lower_table_ddl(self, source_sql: str, source_dialect: str) -> str:
        """Lower table DDL adding GBase 8c distributed sharding key if appropriate."""
        sql = super().lower_table_ddl(source_sql, source_dialect)
        if "PRIMARY KEY" in sql.upper() and "DISTRIBUTE BY" not in sql.upper():
            m = re.search(r"PRIMARY\s+KEY\s*\(([^\)]+)\)", sql, re.IGNORECASE)
            if m:
                pk_col = m.group(1).strip()
                sql = sql.rstrip("; \n") + f" DISTRIBUTE BY HASH({pk_col});"
        return sql

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to GBase 8c PL/pgSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to GBase 8c PL/pgSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to GBase 8c."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = res.replace(":NEW.", "NEW.")
        res = res.replace(":OLD.", "OLD.")
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        res = source_sql
        res = re.sub(
            r"\b([a-zA-Z0-9_]+)\.NEXTVAL\b",
            r"NEXTVAL('\1')",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """Lower package for GBase 8c."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partitioning clause for GBase 8c."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower CREATE INDEX for GBase 8c."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

