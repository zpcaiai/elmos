"""OceanBase (Oracle Mode) Dedicated Target Lowerer.

OceanBase in Oracle mode provides high fidelity compatibility with PL/SQL packages,
stored procedures, triggers, sequences, autonomous transactions, and tablegroups.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class OceanBaseOracleTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for OceanBase in Oracle Mode."""

    target_id = "oceanbase_oracle"
    display_name = "OceanBase (Oracle Mode)"
    family = "oracle_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # T-SQL to OceanBase Oracle
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
            # MySQL to OceanBase Oracle
            "DATETIME": "DATE",
            "LONGTEXT": "CLOB",
            "LONGBLOB": "BLOB",
            "TINYINT": "NUMBER(3)",
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
                rule_id="ob_ora_tablegroup",
                description="Preserve tablegroup hints or add default tablegroup if defined",
                pattern=r"--\s*TABLEGROUP=(\w+)",
                replacement=r"TABLEGROUP = \1",
                is_regex=True,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="ob_ora_square_bracket",
                description="Convert T-SQL [col] to double quotes \"col\"",
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="ob_ora_variable_prefix",
                description="Convert T-SQL @var to v_var",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
        ]

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to OceanBase Oracle mode PL/SQL."""
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
        """Lower function to OceanBase Oracle mode."""
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
        """Lower trigger to OceanBase Oracle mode."""
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
