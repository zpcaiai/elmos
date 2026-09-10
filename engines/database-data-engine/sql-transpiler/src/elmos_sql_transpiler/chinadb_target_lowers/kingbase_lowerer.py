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
                description="Convert T-SQL [col] to Kingbase \"col\"",
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
        ]

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
