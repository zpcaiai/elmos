"""TiDB (PingCAP) Dedicated Target Lowerer.

TiDB provides distributed horizontal scalability with MySQL dialect compatibility.
Handles clustered indexes, placement rules, auto_random, window functions, and transforms
unsupported stored procedures into transactional statement scripts.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class TidbTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for TiDB."""

    target_id = "tidb"
    display_name = "TiDB (v6/v7)"
    family = "mysql_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to TiDB
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
            "BINARY_DOUBLE": "DOUBLE",
            "BINARY_FLOAT": "FLOAT",
            # T-SQL to TiDB
            "DATETIME2": "DATETIME(6)",
            "SMALLDATETIME": "DATETIME",
            "NVARCHAR(MAX)": "LONGTEXT",
            "VARCHAR(MAX)": "LONGTEXT",
            "VARBINARY(MAX)": "LONGBLOB",
            "IMAGE": "LONGBLOB",
            "MONEY": "DECIMAL(19, 4)",
            "SMALLMONEY": "DECIMAL(10, 4)",
            "BIT": "TINYINT(1)",
            "UNIQUEIDENTIFIER": "VARCHAR(36)",
            "XML": "LONGTEXT",
            # PostgreSQL to TiDB
            "BYTEA": "LONGBLOB",
            "TEXT": "LONGTEXT",
            "BOOLEAN": "TINYINT(1)",
            "TIMESTAMPTZ": "TIMESTAMP",
            "UUID": "VARCHAR(36)",
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
            "SYS_GUID": "REPLACE(UUID(), '-', '')",
            "DATEDIFF": "DATEDIFF",
            "DATEADD": "DATE_ADD",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="tidb_backtick_escape",
                description="Convert T-SQL [col] or Oracle \"col\" to TiDB `col`",
                pattern=r"\[([a-zA-Z0-9_]+)\]|\"([a-zA-Z0-9_]+)\"",
                replacement=r"`\1\2`",
                is_regex=True,
                applies_to_dialects=["oracle", "plsql", "tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="tidb_dual_removal",
                description="Strip redundant FROM DUAL in TiDB queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="tidb_auto_increment",
                description="Map IDENTITY(1,1) to AUTO_INCREMENT in TiDB",
                pattern=r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
                replacement="AUTO_INCREMENT",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="tidb_clustered_index",
                description="Inject clustered index hint for high-concurrency primary key tables",
                pattern=r"\bPRIMARY\s+KEY\s*\(([^\)]+)\)",
                replacement=r"PRIMARY KEY (\1) /*T![clustered_index] CLUSTERED */",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
        ]

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedural block to TiDB client-side script or compound statement."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        upper = res.upper()
        if "CREATE PROCEDURE" in upper or "CREATE OR REPLACE PROCEDURE" in upper:
            m = re.search(r"\bBEGIN\b(.*)\bEND\b", res, re.DOTALL | re.IGNORECASE)
            if m:
                inner_body = m.group(1).strip()
                res = (
                    "/* TiDB Lowered Autonomous Procedure Block */\n"
                    f"START TRANSACTION;\n{inner_body}\nCOMMIT;"
                )

        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to TiDB equivalent."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to TiDB application-tier event handler representation."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = f"/* TiDB Application Event Trigger Specification */\n-- {res}"
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        res = source_sql
        res = re.sub(
            r"\b([a-zA-Z0-9_]+)\.NEXTVAL\b",
            r"NEXT VALUE FOR \1",
            res,
            flags=re.IGNORECASE,
        )
        return res
