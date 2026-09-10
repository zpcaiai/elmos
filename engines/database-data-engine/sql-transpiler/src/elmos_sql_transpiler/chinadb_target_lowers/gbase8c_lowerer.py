"""GBase 8c (Distributed openGauss-based) Dedicated Target Lowerer.

GBase 8c provides distributed transactional processing, sharding distribution keys,
and openGauss-compatible procedural capabilities.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GBase8cTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GBase 8c."""

    target_id = "gbase8c"
    display_name = "GBase 8c"
    family = "pg_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to GBase 8c
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
            # T-SQL to GBase 8c
            "DATETIME2": "TIMESTAMP",
            "SMALLDATETIME": "TIMESTAMP",
            "NVARCHAR(MAX)": "TEXT",
            "VARCHAR(MAX)": "TEXT",
            "VARBINARY(MAX)": "BYTEA",
            "IMAGE": "BYTEA",
            "MONEY": "NUMERIC(19, 4)",
            "SMALLMONEY": "NUMERIC(10, 4)",
            "BIT": "BOOLEAN",
            "UNIQUEIDENTIFIER": "UUID",
            # MySQL to GBase 8c
            "DATETIME": "TIMESTAMP",
            "LONGTEXT": "TEXT",
            "MEDIUMTEXT": "TEXT",
            "LONGBLOB": "BYTEA",
            "TINYINT": "SMALLINT",
            "ENUM": "VARCHAR(64)",
            "SET": "VARCHAR(256)",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            "NVL": "COALESCE",
            "ISNULL": "COALESCE",
            "IFNULL": "COALESCE",
            "GETDATE": "CURRENT_TIMESTAMP",
            "GETUTCDATE": "TIMEZONE('UTC', CURRENT_TIMESTAMP)",
            "SYSDATE": "CURRENT_TIMESTAMP",
            "NOW": "CURRENT_TIMESTAMP",
            "LEN": "LENGTH",
            "CHAR_LENGTH": "LENGTH",
            "INSTR": "INSTR",
            "CHARINDEX": "INSTR",
            "NEWID": "MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)::UUID",
            "SYS_GUID": "REPLACE(MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT), '-', '')",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="gbase8c_dual_removal",
                description="Remove FROM DUAL in queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gbase8c_square_brackets",
                description="Convert brackets [col] to GBase 8c \"col\"",
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="gbase8c_variable_prefix",
                description="Convert T-SQL @var to v_var",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
        ]

    def lower_table_ddl(self, source_sql: str, source_dialect: str) -> str:
        """Lower table DDL adding GBase 8c distributed sharding key if appropriate."""
        sql = super().lower_table_ddl(source_sql, source_dialect)
        if "PRIMARY KEY" in sql.upper() and "DISTRIBUTE BY" not in sql.upper():
            m = re.search(r"PRIMARY\s+KEY\s*\(([^\)]+)\)", sql, re.IGNORECASE)
            if m:
                pk_col = m.group(1).strip()
                sql = sql.rstrip("; \n") + f" DISTRIBUTE BY HASH({pk_col});"
        return sql

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to GBase 8c PL/pgSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to GBase 8c PL/pgSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to GBase 8c."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = res.replace(":NEW.", "NEW.")
        res = res.replace(":OLD.", "OLD.")
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        res = source_sql
        res = re.sub(
            r"\b([a-zA-Z0-9_]+)\.NEXTVAL\b",
            r"NEXTVAL('\1')",
            res,
            flags=re.IGNORECASE,
        )
        return res
