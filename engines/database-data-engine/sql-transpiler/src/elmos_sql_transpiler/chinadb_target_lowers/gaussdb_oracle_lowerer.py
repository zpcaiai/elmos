"""Huawei GaussDB (Oracle Mode) Dedicated Target Lowerer.

GaussDB in Oracle mode provides enterprise PL/SQL support, packages, autonomous transactions,
large object (LOB) handling, synonyms, and high performance distributed query execution.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GaussDbOracleTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GaussDB in Oracle Mode."""

    target_id = "gaussdb_oracle"
    display_name = "GaussDB (Oracle Mode)"
    family = "oracle_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # T-SQL to GaussDB Oracle
            "DATETIME2": "TIMESTAMP",
            "SMALLDATETIME": "TIMESTAMP",
            "NVARCHAR(MAX)": "CLOB",
            "VARCHAR(MAX)": "CLOB",
            "VARBINARY(MAX)": "BLOB",
            "IMAGE": "BLOB",
            "MONEY": "NUMBER(19, 4)",
            "SMALLMONEY": "NUMBER(10, 4)",
            "BIT": "NUMBER(1)",
            "UNIQUEIDENTIFIER": "VARCHAR2(36)",
            # MySQL to GaussDB Oracle
            "DATETIME": "DATE",
            "LONGTEXT": "CLOB",
            "LONGBLOB": "BLOB",
            "DOUBLE": "BINARY_DOUBLE",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            "GETDATE": "SYSDATE",
            "GETUTCDATE": "SYS_EXTRACT_UTC(SYSTIMESTAMP)",
            "ISNULL": "NVL",
            "IFNULL": "NVL",
            "LEN": "LENGTH",
            "CHAR_LENGTH": "LENGTH",
            "CHARINDEX": "INSTR",
            "LOCATE": "INSTR",
            "NEWID": "SYS_GUID()",
            "NOW": "SYSDATE",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="gauss_ora_identity",
                description="Normalize identity / sequence syntax",
                pattern=r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
                replacement="GENERATED ALWAYS AS IDENTITY",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="gauss_ora_brackets",
                description='Convert T-SQL brackets [col] to double quotes "col"',
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="gauss_ora_variables",
                description="Convert T-SQL @var to v_var",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="gauss_ora_autonomous_trans",
                description="Preserve GaussDB Oracle mode autonomous transaction PRAGMA",
                pattern=r"PRAGMA\s+AUTONOMOUS_TRANSACTION\s*;",
                replacement="PRAGMA AUTONOMOUS_TRANSACTION;",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="gauss_ora_forall",
                description="Preserve FORALL bulk statement in GaussDB Oracle mode",
                pattern=r"\bFORALL\s+([a-zA-Z0-9_]+)\s+IN\s+([^\n]+)",
                replacement=r"FORALL \1 IN \2",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """GaussDB Oracle mode returns Oracle-compatible ORA- error codes."""
        return {
            "23505": "ORA-00001",
            "42P01": "ORA-00942",
            "42703": "ORA-00904",
            "1062": "ORA-00001",
            "1146": "ORA-00942",
            "1054": "ORA-00904",
            "2627": "ORA-00001",
            "208": "ORA-00942",
        }

    def _build_catalog_queries(self) -> dict[str, str]:
        """GaussDB Oracle mode data dictionary views."""
        return {
            "tables": "SELECT TABLE_NAME FROM USER_TABLES ORDER BY TABLE_NAME",
            "columns": (
                "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, "
                "DATA_SCALE, NULLABLE FROM USER_TAB_COLUMNS "
                "WHERE TABLE_NAME = :tab_name ORDER BY COLUMN_ID"
            ),
            "indexes": (
                "SELECT INDEX_NAME, TABLE_NAME, UNIQUENESS FROM USER_INDEXES "
                "WHERE TABLE_NAME = :tab_name"
            ),
            "constraints": (
                "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE, TABLE_NAME "
                "FROM USER_CONSTRAINTS WHERE TABLE_NAME = :tab_name"
            ),
            "procedures": (
                "SELECT OBJECT_NAME FROM USER_OBJECTS "
                "WHERE OBJECT_TYPE IN ('PROCEDURE', 'FUNCTION', 'PACKAGE') ORDER BY OBJECT_NAME"
            ),
            "sequences": (
                "SELECT SEQUENCE_NAME, MIN_VALUE, MAX_VALUE, INCREMENT_BY, LAST_NUMBER "
                "FROM USER_SEQUENCES"
            ),
            "partitions": (
                "SELECT TABLE_NAME, PARTITION_NAME, HIGH_VALUE "
                "FROM USER_TAB_PARTITIONS WHERE TABLE_NAME = :tab_name"
            ),
        }

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to GaussDB Oracle mode PL/SQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = re.sub(
            r"\bCREATE\s+PROCEDURE\b",
            "CREATE OR REPLACE PROCEDURE",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to GaussDB Oracle mode."""
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
        """Lower trigger to GaussDB Oracle mode."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = re.sub(
            r"\bCREATE\s+TRIGGER\b",
            "CREATE OR REPLACE TRIGGER",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        return source_sql

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """GaussDB Oracle mode natively supports PACKAGE specifications and bodies."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partitioning clause for GaussDB Oracle."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index definition for GaussDB Oracle."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res
