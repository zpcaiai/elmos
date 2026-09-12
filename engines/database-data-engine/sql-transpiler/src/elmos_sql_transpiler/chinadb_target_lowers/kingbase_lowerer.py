"""KingbaseES (V8/V9) Dedicated Target Lowerer.

KingbaseES provides dual Oracle and PostgreSQL compatibility modes.
Supports PL/SQL extensions, sys_guid(), tablespaces, and robust procedural blocks.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class KingbaseTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for KingbaseES."""

    target_id = "kingbase"
    display_name = "KingbaseES (V8/V9)"
    family = "oracle_pg_hybrid"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to Kingbase
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
            "BFILE": "VARCHAR(256)",
            # T-SQL to Kingbase
            "DATETIME2": "TIMESTAMP",
            "SMALLDATETIME": "TIMESTAMP",
            "NVARCHAR(MAX)": "TEXT",
            "VARCHAR(MAX)": "TEXT",
            "VARBINARY(MAX)": "BYTEA",
            "IMAGE": "BYTEA",
            "MONEY": "NUMERIC(19, 4)",
            "SMALLMONEY": "NUMERIC(10, 4)",
            "BIT": "BOOLEAN",
            "UNIQUEIDENTIFIER": "VARCHAR(36)",
            "SQL_VARIANT": "VARCHAR(2000)",
            "XML": "XML",
            # MySQL to Kingbase
            "DATETIME": "TIMESTAMP",
            "LONGTEXT": "TEXT",
            "MEDIUMTEXT": "TEXT",
            "TINYTEXT": "VARCHAR(255)",
            "LONGBLOB": "BYTEA",
            "MEDIUMBLOB": "BYTEA",
            "TINYBLOB": "BYTEA",
            "ENUM": "VARCHAR(64)",
            "SET": "VARCHAR(256)",
            "TINYINT": "SMALLINT",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            # Oracle builtins in Kingbase standard mode
            "NVL": "COALESCE",
            "ISNULL": "COALESCE",
            "IFNULL": "COALESCE",
            "GETDATE": "CURRENT_TIMESTAMP",
            "GETUTCDATE": "TIMEZONE('UTC', CURRENT_TIMESTAMP)",
            "SYSDATE": "CURRENT_TIMESTAMP",
            "NOW": "CURRENT_TIMESTAMP",
            "LEN": "LENGTH",
            "CHAR_LENGTH": "LENGTH",
            "CHARINDEX": "INSTR",
            "LOCATE": "INSTR",
            "NEWID": "SYS_GUID()",
            "UUID": "SYS_GUID()",
            "DATEDIFF": "KB_DATEDIFF",
            "DATEADD": "KB_DATEADD",
            "CONCAT_WS": "CONCAT_WS",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="kb_nvl2_to_case",
                description="Convert NVL2(a, b, c) to CASE WHEN a IS NOT NULL THEN b ELSE c END",
                pattern=r"\bNVL2\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,\)]+)\s*\)",
                replacement=r"CASE WHEN \1 IS NOT NULL THEN \2 ELSE \3 END",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="kb_dual_strip",
                description="Kingbase can query without FROM DUAL in standard mode",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="kb_tsql_variable_prefix",
                description="Replace T-SQL @variable with v_variable for Kingbase procedural code",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="kb_square_brackets",
                description='Convert T-SQL [col] to Kingbase "col"',
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="kb_limit_offset",
                description="Normalize pagination to LIMIT n OFFSET m",
                pattern=r"\bOFFSET\s+(\d+)\s+ROWS\s+FETCH\s+NEXT\s+(\d+)\s+ROWS\s+ONLY",
                replacement=r"LIMIT \2 OFFSET \1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="kb_auto_increment",
                description="Map AUTO_INCREMENT or IDENTITY to Kingbase SERIAL",
                pattern=r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)|\bAUTO_INCREMENT\b",
                replacement="GENERATED ALWAYS AS IDENTITY",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver", "mysql"],
            ),
            DialectLoweringRule(
                rule_id="kb_pragma_autonomous",
                description="Kingbase autonomous transaction pragma mapping",
                pattern=r"PRAGMA\s+AUTONOMOUS_TRANSACTION\s*;",
                replacement="PRAGMA AUTONOMOUS_TRANSACTION;",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="kb_try_catch_block",
                description="Convert T-SQL BEGIN TRY ... END TRY to Kingbase EXCEPTION block",
                pattern=r"\bBEGIN\s+TRY\b([\s\S]*?)\bEND\s+TRY\s+BEGIN\s+CATCH\b([\s\S]*?)\bEND\s+CATCH\b",
                replacement=r"BEGIN\1EXCEPTION WHEN OTHERS THEN\2END;",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="kb_partition_by_range",
                description="Preserve Kingbase native range partitioning",
                pattern=r"\bPARTITION\s+BY\s+RANGE\s*\(([^\)]+)\)",
                replacement=r"PARTITION BY RANGE (\1)",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="kb_string_agg",
                description="Convert GROUP_CONCAT to STRING_AGG in Kingbase",
                pattern=r"\bGROUP_CONCAT\s*\(\s*([^,\)]+)\s*(?:SEPARATOR\s*'([^']+)')?\s*\)",
                replacement=r"STRING_AGG(\1, COALESCE('\2', ','))",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
            DialectLoweringRule(
                rule_id="kb_for_update_skip_locked",
                description="Ensure SKIP LOCKED / NOWAIT syntax is valid in Kingbase",
                pattern=r"\bFOR\s+UPDATE\s+SKIP\s+LOCKED\b",
                replacement="FOR UPDATE SKIP LOCKED",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "postgres"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Map legacy DBMS error codes to Kingbase SQLSTATE codes."""
        return {
            "ORA-00001": "23505",  # unique_violation
            "ORA-00942": "42P01",  # undefined_table
            "ORA-00904": "42703",  # undefined_column
            "ORA-01400": "23502",  # not_null_violation
            "ORA-01403": "P0002",  # no_data_found
            "ORA-02291": "23503",  # foreign_key_violation
            "ORA-02292": "23503",  # foreign_key_violation
            "1062": "23505",  # MySQL duplicate key
            "1146": "42P01",  # MySQL no such table
            "1054": "42703",  # MySQL bad field
            "2627": "23505",  # T-SQL PK violation
            "208": "42P01",  # T-SQL invalid object
        }

    def _build_catalog_queries(self) -> dict[str, str]:
        """Kingbase data dictionary views (supports sys_class/pg_class)."""
        return {
            "tables": (
                "SELECT relname AS table_name FROM sys_class "
                "WHERE relkind = 'r' AND relnamespace = "
                "(SELECT oid FROM sys_namespace WHERE nspname = current_schema()) "
                "ORDER BY relname"
            ),
            "columns": (
                "SELECT column_name, data_type, character_maximum_length, "
                "numeric_precision, numeric_scale, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :tab_name "
                "ORDER BY ordinal_position"
            ),
            "indexes": (
                "SELECT indexname AS index_name, tablename AS table_name "
                "FROM sys_indexes WHERE schemaname = current_schema() "
                "AND tablename = :tab_name"
            ),
            "constraints": (
                "SELECT conname AS constraint_name, contype AS constraint_type "
                "FROM sys_constraint WHERE conrelid = :tab_name::regclass"
            ),
            "procedures": (
                "SELECT proname AS routine_name FROM sys_proc "
                "WHERE pronamespace = (SELECT oid FROM sys_namespace "
                "WHERE nspname = current_schema())"
            ),
            "sequences": (
                "SELECT sequence_name, start_value, increment, last_value "
                "FROM information_schema.sequences WHERE sequence_schema = current_schema()"
            ),
            "triggers": (
                "SELECT trigger_name, event_manipulation, event_object_table, "
                "action_statement FROM information_schema.triggers "
                "WHERE trigger_schema = current_schema()"
            ),
        }

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to Kingbase procedural dialect (PL/SQL or PL/pgSQL)."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        res = re.sub(
            r"\bCREATE\s+PROCEDURE\b",
            "CREATE OR REPLACE PROCEDURE",
            res,
            flags=re.IGNORECASE,
        )
        if not res.strip().endswith(";"):
            res = res.strip() + ";"

        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function declaration to Kingbase."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = re.sub(
            r"\bCREATE\s+FUNCTION\b",
            "CREATE OR REPLACE FUNCTION",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger declaration to Kingbase."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and usage."""
        res = source_sql
        res = re.sub(
            r"\b([a-zA-Z0-9_]+)\.NEXTVAL\b",
            r"NEXTVAL('\1')",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """Lower Oracle PL/SQL package for Kingbase PL/KSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower partition definition to Kingbase declarative partitioning."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index definition to Kingbase."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res
