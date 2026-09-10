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
            DialectLoweringRule(
                rule_id="ob_ora_tablegroup",
                description="Inject OceanBase TABLEGROUP hint for co-located partitions",
                pattern=r"/\*\s*TABLEGROUP\s*=\s*([a-zA-Z0-9_]+)\s*\*/",
                replacement=r"TABLEGROUP = '\1'",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="ob_ora_autonomous_trans",
                description="Preserve OceanBase Oracle autonomous transaction PRAGMA",
                pattern=r"PRAGMA\s+AUTONOMOUS_TRANSACTION\s*;",
                replacement="PRAGMA AUTONOMOUS_TRANSACTION;",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """OceanBase Oracle mode returns Oracle-compatible ORA- error codes."""
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
        """OceanBase Oracle mode data dictionary views."""
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

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """OceanBase Oracle mode natively supports PACKAGE specifications and bodies."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partitioning clause for OceanBase Oracle."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index definition for OceanBase Oracle."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

