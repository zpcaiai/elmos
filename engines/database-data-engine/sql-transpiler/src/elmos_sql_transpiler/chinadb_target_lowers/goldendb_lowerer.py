"""ZTE GoldenDB Dedicated Target Lowerer.

GoldenDB is a distributed financial transactional database providing GTID consistency,
distributed partition routing comments (/*+db_shard()*/), and MySQL syntax compatibility.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GoldenDbTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GoldenDB."""

    target_id = "goldendb"
    display_name = "ZTE GoldenDB"
    family = "mysql_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to GoldenDB
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
                rule_id="goldendb_sharding_comment",
                description="Inject distributed sharding comment into queries with primary keys",
                pattern=r"--\s*SHARD_KEY=([a-zA-Z0-9_]+)",
                replacement=r"/*+db_shard(\1)*/",
                is_regex=True,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="goldendb_backtick_escape",
                description="Convert brackets [col] or Oracle \"col\" to MySQL backticks `col`",
                pattern=r"\[([a-zA-Z0-9_]+)\]|\"([a-zA-Z0-9_]+)\"",
                replacement=r"`\1\2`",
                is_regex=True,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="goldendb_dual_strip",
                description="Remove FROM DUAL in standard queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
        ]

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to GoldenDB stored procedure."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to GoldenDB."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to GoldenDB."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        return source_sql
