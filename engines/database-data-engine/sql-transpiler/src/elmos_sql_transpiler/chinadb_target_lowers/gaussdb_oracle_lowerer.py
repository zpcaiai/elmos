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
                description="Convert T-SQL brackets [col] to double quotes \"col\"",
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
        ]

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
