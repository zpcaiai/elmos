"""openGauss / MogDB Dedicated Target Lowerer.

openGauss provides enterprise relational capabilities based on an enhanced PL/pgSQL
procedural engine, row/column orientation, distribution keys, and vector execution.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class OpenGaussTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for openGauss and MogDB."""

    target_id = "opengauss"
    display_name = "openGauss / MogDB"
    family = "pg_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to openGauss
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
            "ROWID": "VARCHAR(64)",
            # T-SQL to openGauss
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
            # MySQL to openGauss
            "DATETIME": "TIMESTAMP",
            "LONGTEXT": "TEXT",
            "MEDIUMTEXT": "TEXT",
            "TINYTEXT": "VARCHAR(255)",
            "LONGBLOB": "BYTEA",
            "MEDIUMBLOB": "BYTEA",
            "TINYBLOB": "BYTEA",
            "DOUBLE": "DOUBLE PRECISION",
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
            "LOCATE": "INSTR",
            "NEWID": "MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)::UUID",
            "SYS_GUID": "REPLACE(MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT), '-', '')",
            "UUID": "MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)::UUID",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="og_dual_removal",
                description="Remove FROM DUAL in openGauss queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="og_square_brackets",
                description='Convert T-SQL [col] to openGauss "col"',
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="og_variable_prefix",
                description="Convert T-SQL @var to v_var in openGauss",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="og_limit_offset",
                description="Standardize LIMIT and OFFSET clauses",
                pattern=r"\bOFFSET\s+(\d+)\s+ROWS\s+FETCH\s+NEXT\s+(\d+)\s+ROWS\s+ONLY",
                replacement=r"LIMIT \2 OFFSET \1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="og_autonomous_trans",
                description="openGauss natively supports PRAGMA AUTONOMOUS_TRANSACTION in PL/pgSQL",
                pattern=r"PRAGMA\s+AUTONOMOUS_TRANSACTION\s*;",
                replacement="PRAGMA AUTONOMOUS_TRANSACTION;",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="og_partition_by_range",
                description="Preserve openGauss partition by range with interval option",
                pattern=r"\bPARTITION\s+BY\s+RANGE\s*\(([^\)]+)\)",
                replacement=r"PARTITION BY RANGE (\1)",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="og_string_agg",
                description="Convert GROUP_CONCAT to STRING_AGG in openGauss",
                pattern=r"\bGROUP_CONCAT\s*\(\s*([^,\)]+)\s*(?:SEPARATOR\s*'([^']+)')?\s*\)",
                replacement=r"STRING_AGG(\1, COALESCE('\2', ','))",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
            DialectLoweringRule(
                rule_id="og_lock_mode",
                description="Ensure FOR UPDATE SKIP LOCKED is valid in openGauss",
                pattern=r"\bFOR\s+UPDATE\s+SKIP\s+LOCKED\b",
                replacement="FOR UPDATE SKIP LOCKED",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "postgres"],
            ),
            DialectLoweringRule(
                rule_id="og_row_number_over",
                description="Support standard window functions in openGauss",
                pattern=r"\bROW_NUMBER\s*\(\s*\)\s*OVER\s*\(",
                replacement="ROW_NUMBER() OVER (",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Map legacy DBMS error codes to openGauss SQLSTATE codes."""
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
        """openGauss catalog inspection queries."""
        return {
            "tables": (
                "SELECT tablename AS table_name FROM pg_tables "
                "WHERE schemaname = current_schema() ORDER BY tablename"
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
            "sequences": (
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = current_schema()"
            ),
            "partitions": (
                "SELECT relname AS partition_name, partstrat FROM pg_partition "
                "WHERE parentid = :tab_name::regclass"
            ),
        }

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to openGauss PL/pgSQL dialect with $$ envelope."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        if "$$" not in res and "BEGIN" in res.upper():
            m = re.search(
                r"(CREATE(?:\s+OR\s+REPLACE)?\s+PROCEDURE\s+[^\(]+(?:\([^\)]*\))?)\s+(?:AS|IS)\s*(.*)\bBEGIN\b(.*)\bEND\s*;?",
                res,
                re.DOTALL | re.IGNORECASE,
            )
            if m:
                header = m.group(1)
                decl = m.group(2).strip()
                body = m.group(3).strip()
                decl_block = f"DECLARE\n{decl}\n" if decl else ""
                res = f"{header}\nAS $$\n{decl_block}BEGIN\n{body}\nEND;\n$$ LANGUAGE plpgsql;"

        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function declaration to openGauss PL/pgSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        if "$$" not in res and "BEGIN" in res.upper():
            m = re.search(
                r"(CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION\s+[^\(]+\([^\)]*\)\s+RETURNS?\s+[a-zA-Z0-9_\(\)]+)\s+(?:AS|IS)\s*(.*)\bBEGIN\b(.*)\bEND\s*;?",
                res,
                re.DOTALL | re.IGNORECASE,
            )
            if m:
                header = m.group(1)
                decl = m.group(2).strip()
                body = m.group(3).strip()
                decl_block = f"DECLARE\n{decl}\n" if decl else ""
                res = f"{header}\nAS $$\n{decl_block}BEGIN\n{body}\nEND;\n$$ LANGUAGE plpgsql;"

        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to openGauss trigger function + trigger creation."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = res.replace(":NEW.", "NEW.")
        res = res.replace(":OLD.", "OLD.")
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and references."""
        res = source_sql
        res = re.sub(
            r"\b([a-zA-Z0-9_]+)\.NEXTVAL\b",
            r"NEXTVAL('\1')",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """openGauss supports PACKAGE mechanism natively in A-mode (Oracle mode)."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partition clause to openGauss partition by range/hash."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower CREATE INDEX for openGauss."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res
