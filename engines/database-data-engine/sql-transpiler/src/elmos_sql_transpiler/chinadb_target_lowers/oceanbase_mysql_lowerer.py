"""OceanBase (MySQL Mode) Dedicated Target Lowerer.

OceanBase in MySQL mode provides distributed horizontal scale with MySQL dialect fidelity,
partition tablegroups, and high-performance distributed sequence and index semantics.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class OceanBaseMysqlTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for OceanBase in MySQL Mode."""

    target_id = "oceanbase_mysql"
    display_name = "OceanBase (MySQL Mode)"
    family = "mysql_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to OceanBase MySQL
            "VARCHAR2": "VARCHAR",
            "NVARCHAR2": "VARCHAR",
            "NUMBER": "DECIMAL",
            "CLOB": "LONGTEXT",
            "NCLOB": "LONGTEXT",
            "BLOB": "LONGBLOB",
            "RAW": "VARBINARY",
            "LONG RAW": "LONGBLOB",
            "DATETIME2": "DATETIME(6)",
            "SMALLDATETIME": "DATETIME",
            "MONEY": "DECIMAL(19, 4)",
            "SMALLMONEY": "DECIMAL(10, 4)",
            "BIT": "TINYINT(1)",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            "NVL": "IFNULL",
            "ISNULL": "IFNULL",
            "GETDATE": "NOW",
            "GETUTCDATE": "UTC_TIMESTAMP",
            "SYSDATE": "NOW",
            "LEN": "CHAR_LENGTH",
            "LENGTH": "CHAR_LENGTH",
            "INSTR": "LOCATE",
            "NEWID": "UUID",
            "SYS_GUID": "REPLACE(UUID(), '-', '')",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="ob_mysql_backtick",
                description="Convert brackets [col] or Oracle \"col\" to MySQL backticks `col`",
                pattern=r"\[([a-zA-Z0-9_]+)\]|\"([a-zA-Z0-9_]+)\"",
                replacement=r"`\1\2`",
                is_regex=True,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="ob_mysql_dual_strip",
                description="Remove FROM DUAL",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="ob_mysql_tablegroup",
                description="Inject OceanBase TABLEGROUP hint in MySQL mode",
                pattern=r"/\*\s*TABLEGROUP\s*=\s*([a-zA-Z0-9_]+)\s*\*/",
                replacement=r"TABLEGROUP = `\1`",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="ob_mysql_auto_inc",
                description="Convert IDENTITY to AUTO_INCREMENT",
                pattern=r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
                replacement="AUTO_INCREMENT",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Translate error codes to OceanBase MySQL mode error codes."""
        return {
            "ORA-00001": "1062",
            "ORA-00942": "1146",
            "ORA-00904": "1054",
            "ORA-01400": "1048",
            "23505": "1062",
            "42P01": "1146",
            "42703": "1054",
            "2627": "1062",
            "208": "1146",
        }

    def _build_catalog_queries(self) -> dict[str, str]:
        """OceanBase MySQL mode catalog inspection queries."""
        return {
            "tables": (
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
            ),
            "columns": (
                "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, "
                "NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tab_name "
                "ORDER BY ORDINAL_POSITION"
            ),
            "indexes": (
                "SELECT INDEX_NAME, TABLE_NAME, NON_UNIQUE "
                "FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tab_name"
            ),
            "partitions": (
                "SELECT PARTITION_NAME, PARTITION_EXPRESSION, TABLE_ROWS "
                "FROM INFORMATION_SCHEMA.PARTITIONS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tab_name"
            ),
        }

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to OceanBase MySQL stored procedure or compound script."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to OceanBase MySQL mode."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to OceanBase MySQL mode."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        return source_sql

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """Lower package for OceanBase MySQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partitioning for OceanBase MySQL."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index definition for OceanBase MySQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

