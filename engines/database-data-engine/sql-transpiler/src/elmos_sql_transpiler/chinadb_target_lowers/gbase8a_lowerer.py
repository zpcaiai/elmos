"""GBase 8a MPP Analytical Database Target Lowerer.

GBase 8a is an analytical columnar MPP database. Converts row-oriented procedural patterns
into bulk set-based analytics, applies DISTRIBUTED BY hashing, and adapts columnar types.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GBase8aTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GBase 8a."""

    target_id = "gbase8a"
    display_name = "GBase 8a (MPP)"
    family = "mpp"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to GBase 8a
            "VARCHAR2": "VARCHAR",
            "NVARCHAR2": "VARCHAR",
            "NUMBER": "DECIMAL",
            "CLOB": "LONGTEXT",
            "NCLOB": "LONGTEXT",
            "BLOB": "LONGBLOB",
            "RAW": "VARBINARY",
            "LONG RAW": "LONGBLOB",
            "LONG": "LONGTEXT",
            "ROWID": "VARCHAR(64)",
            # T-SQL to GBase 8a
            "DATETIME2": "DATETIME",
            "SMALLDATETIME": "DATETIME",
            "NVARCHAR(MAX)": "LONGTEXT",
            "VARCHAR(MAX)": "LONGTEXT",
            "VARBINARY(MAX)": "LONGBLOB",
            "IMAGE": "LONGBLOB",
            "MONEY": "DECIMAL(19, 4)",
            "SMALLMONEY": "DECIMAL(10, 4)",
            "BIT": "TINYINT",
            # PostgreSQL to GBase 8a
            "BYTEA": "LONGBLOB",
            "TEXT": "LONGTEXT",
            "BOOLEAN": "TINYINT",
            "TIMESTAMPTZ": "DATETIME",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            "NVL": "IFNULL",
            "ISNULL": "IFNULL",
            "COALESCE": "COALESCE",
            "GETDATE": "NOW",
            "GETUTCDATE": "UTC_TIMESTAMP",
            "SYSDATE": "NOW",
            "LEN": "CHAR_LENGTH",
            "LENGTH": "CHAR_LENGTH",
            "INSTR": "LOCATE",
            "CHARINDEX": "LOCATE",
            "NEWID": "UUID",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="gbase8a_dual_removal",
                description="Remove FROM DUAL in queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gbase8a_backtick_escape",
                description="Escape identifiers with backticks",
                pattern=r"\[([a-zA-Z0-9_]+)\]|\"([a-zA-Z0-9_]+)\"",
                replacement=r"`\1\2`",
                is_regex=True,
                applies_to_dialects=["all"],
            ),
        ]

    def lower_table_ddl(self, source_sql: str, source_dialect: str) -> str:
        """Lower table DDL adding GBase 8a MPP DISTRIBUTED BY clause."""
        sql = super().lower_table_ddl(source_sql, source_dialect)
        if "DISTRIBUTED BY" not in sql.upper():
            m = re.search(r"PRIMARY\s+KEY\s*\(([^\)]+)\)", sql, re.IGNORECASE)
            if m:
                pk_col = m.group(1).strip().strip("`'\"")
                sql = sql.rstrip("; \n") + f" DISTRIBUTED BY ('{pk_col}');"
        return sql

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure for GBase 8a analytical batches."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function for GBase 8a."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger into GBase 8a comment notation."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return f"/* GBase 8a MPP Batch Validation Trigger */\n-- {res}"

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation."""
        return source_sql
