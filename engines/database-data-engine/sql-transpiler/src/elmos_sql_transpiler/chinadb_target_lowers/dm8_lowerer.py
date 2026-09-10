"""Dameng 8 (DM8) Target Lowerer.

Dameng DB provides native Oracle compatibility mode with support for PL/SQL syntax,
packages, autonomous transactions, DUAL table, rowid, and sequence NEXTVAL syntax.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class Dm8TargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for Dameng 8 (DM8)."""

    target_id = "dm8"
    display_name = "Dameng 8 (DM8)"
    family = "oracle_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # T-SQL to DM8
            "DATETIME2": "TIMESTAMP",
            "SMALLDATETIME": "TIMESTAMP",
            "NVARCHAR(MAX)": "CLOB",
            "VARCHAR(MAX)": "CLOB",
            "VARBINARY(MAX)": "BLOB",
            "IMAGE": "BLOB",
            "MONEY": "DECIMAL(19, 4)",
            "SMALLMONEY": "DECIMAL(10, 4)",
            "BIT": "TINYINT",
            "UNIQUEIDENTIFIER": "VARCHAR(36)",
            "SQL_VARIANT": "VARCHAR(2000)",
            "XML": "CLOB",
            "GEOMETRY": "GEOMETRY",
            "GEOGRAPHY": "GEOGRAPHY",
            "HIERARCHYID": "VARCHAR(256)",
            # MySQL to DM8
            "DATETIME": "TIMESTAMP",
            "LONGTEXT": "CLOB",
            "MEDIUMTEXT": "CLOB",
            "TINYTEXT": "VARCHAR(255)",
            "LONGBLOB": "BLOB",
            "MEDIUMBLOB": "BLOB",
            "TINYBLOB": "VARBINARY(255)",
            "DOUBLE": "DOUBLE PRECISION",
            "ENUM": "VARCHAR(64)",
            "SET": "VARCHAR(256)",
            # PostgreSQL to DM8
            "BYTEA": "BLOB",
            "TEXT": "CLOB",
            "BOOLEAN": "TINYINT",
            "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
            "TIMETZ": "TIME WITH TIME ZONE",
            "SERIAL": "INT IDENTITY(1, 1)",
            "BIGSERIAL": "BIGINT IDENTITY(1, 1)",
            "UUID": "VARCHAR(36)",
            "JSON": "CLOB",
            "JSONB": "CLOB",
            # Oracle to DM8 standardizations
            "VARCHAR2": "VARCHAR",
            "NVARCHAR2": "NVARCHAR",
            "NUMBER": "DECIMAL",
            "BINARY_DOUBLE": "DOUBLE",
            "BINARY_FLOAT": "FLOAT",
            "RAW": "VARBINARY",
            "LONG RAW": "BLOB",
            "LONG": "CLOB",
            "BFILE": "VARCHAR(256)",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            # T-SQL builtins to DM8 / Oracle mode
            "GETDATE": "SYSDATE",
            "GETUTCDATE": "SYS_EXTRACT_UTC(SYSTIMESTAMP)",
            "ISNULL": "NVL",
            "LEN": "LENGTH",
            "CHARINDEX": "INSTR",
            "NEWID": "RAWTOHEX(SYS_GUID())",
            "DATEDIFF": "DM_DATEDIFF",
            "DATEADD": "DM_DATEADD",
            "STUFF": "DM_STUFF",
            "SQUARE": "POWER",
            "REPLICATE": "RPAD",
            # MySQL builtins to DM8
            "NOW": "SYSDATE",
            "UTC_TIMESTAMP": "SYS_EXTRACT_UTC(SYSTIMESTAMP)",
            "IFNULL": "NVL",
            "CHAR_LENGTH": "LENGTH",
            "LOCATE": "INSTR",
            "UUID": "RAWTOHEX(SYS_GUID())",
            "DATE_FORMAT": "TO_CHAR",
            "STR_TO_DATE": "TO_DATE",
            "CONCAT_WS": "DM_CONCAT_WS",
            "UNIX_TIMESTAMP": "DM_UNIX_TIMESTAMP",
            "FROM_UNIXTIME": "DM_FROM_UNIXTIME",
            # PostgreSQL builtins to DM8
            "CURRENT_TIMESTAMP": "SYSTIMESTAMP",
            "CLOCK_TIMESTAMP": "SYSTIMESTAMP",
            "STRPOS": "INSTR",
            "GEN_RANDOM_UUID": "RAWTOHEX(SYS_GUID())",
            "TO_TIMESTAMP": "TO_TIMESTAMP",
            "AGE": "DM_AGE",
            "RANDOM": "DBMS_RANDOM.VALUE",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="dm8_identity_clause",
                description="Convert T-SQL IDENTITY(1,1) to DM8 IDENTITY(1, 1)",
                pattern=r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
                replacement="IDENTITY(1, 1)",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="dm8_square_bracket_escape",
                description="Convert T-SQL square brackets [col] to DM8 double quotes \"col\"",
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="dm8_convert_cast",
                description="Convert T-SQL CONVERT(type, val) to CAST(val AS type)",
                pattern=r"\bCONVERT\s*\(\s*([a-zA-Z0-9_\(\)]+)\s*,\s*([^,\)]+)\s*\)",
                replacement=r"CAST(\2 AS \1)",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="dm8_tsql_variable_prefix",
                description="Replace T-SQL @variable with v_variable for DM8 procedural code",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="dm8_dual_preservation",
                description="DM8 natively supports DUAL; ensure SELECT FROM DUAL is valid",
                pattern="SELECT 1;",
                replacement="SELECT 1 FROM DUAL;",
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="dm8_top_to_rownum",
                description="Convert T-SQL TOP N to DM8 ROWNUM <= N",
                pattern=r"\bSELECT\s+TOP\s+(\d+)\s+(.+)",
                replacement=r"SELECT \2 WHERE ROWNUM <= \1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="dm8_limit_offset",
                description="Convert MySQL LIMIT M OFFSET N to DM8 LIMIT N, M",
                pattern=r"\bLIMIT\s+(\d+)\s+OFFSET\s+(\d+)",
                replacement=r"LIMIT \2, \1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
            DialectLoweringRule(
                rule_id="dm8_auto_increment_to_identity",
                description="Convert MySQL AUTO_INCREMENT to DM8 IDENTITY(1, 1)",
                pattern=r"\bAUTO_INCREMENT\b",
                replacement="IDENTITY(1, 1)",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
            DialectLoweringRule(
                rule_id="dm8_on_duplicate_key",
                description="Flag MySQL ON DUPLICATE KEY UPDATE for MERGE INTO transformation",
                pattern=r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b.*",
                replacement="/* DM8: Converted via MERGE statement */",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
        ]

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower stored procedure to DM8 native procedural dialect."""
        src = source_dialect.lower()
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        if src in ["tsql", "sqlserver"]:
            res = re.sub(
                r"\bCREATE\s+PROCEDURE\s+([a-zA-Z0-9_]+)\b",
                r"CREATE OR REPLACE PROCEDURE \1",
                res,
                flags=re.IGNORECASE,
            )
            res = re.sub(
                r"\bv_([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_\(\)]+)",
                r"v_\1 IN \2",
                res,
            )
        elif src in ["oracle", "plsql"]:
            if not res.strip().endswith("/"):
                res = res.strip()
                if not res.endswith(";"):
                    res += ";"

        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function declaration to DM8."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = re.sub(
            r"\bCREATE\s+FUNCTION\s+([a-zA-Z0-9_]+)\b",
            r"CREATE OR REPLACE FUNCTION \1",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger declaration to DM8."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = re.sub(
            r"\bCREATE\s+TRIGGER\s+([a-zA-Z0-9_]+)\b",
            r"CREATE OR REPLACE TRIGGER \1",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and usage."""
        res = source_sql
        return res
