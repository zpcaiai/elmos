"""Huawei GaussDB (MySQL Mode) Dedicated Target Lowerer.

GaussDB in MySQL mode provides distributed partition tables, online schema changes,
read-replica query routing, and MySQL dialect compatibility.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GaussDbMysqlTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GaussDB in MySQL Mode."""

    target_id = "gaussdb_mysql"
    display_name = "GaussDB (MySQL Mode)"
    family = "mysql_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to GaussDB MySQL
            "VARCHAR2": "VARCHAR",
            "NVARCHAR2": "VARCHAR",
            "NUMBER": "DECIMAL",
            "CLOB": "LONGTEXT",
            "NCLOB": "LONGTEXT",
            "BLOB": "LONGBLOB",
            "RAW": "VARBINARY",
            "DATETIME2": "DATETIME(6)",
            "MONEY": "DECIMAL(19, 4)",
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
                rule_id="gauss_mysql_backticks",
                description="Convert brackets to backticks",
                pattern=r"\[([a-zA-Z0-9_]+)\]|\"([a-zA-Z0-9_]+)\"",
                replacement=r"`\1\2`",
                is_regex=True,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gauss_mysql_dual_strip",
                description="Strip redundant FROM DUAL in queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gauss_mysql_auto_inc",
                description="Map IDENTITY to AUTO_INCREMENT in GaussDB MySQL mode",
                pattern=r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
                replacement="AUTO_INCREMENT",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Translate error codes to GaussDB MySQL mode error codes."""
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
        """GaussDB MySQL mode catalog inspection queries."""
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
        """Lower procedure to GaussDB MySQL mode."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to GaussDB MySQL mode."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to GaussDB MySQL mode."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        return source_sql

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """Lower package for GaussDB MySQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partitioning for GaussDB MySQL."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index definition for GaussDB MySQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res
