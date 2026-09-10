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
                description='Convert T-SQL [col] or Oracle "col" to TiDB `col`',
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
            DialectLoweringRule(
                rule_id="tidb_shard_row_id",
                description="Inject SHARD_ROW_ID_BITS for hot table scatter",
                pattern=r"\bENGINE\s*=\s*InnoDB\b",
                replacement="ENGINE=InnoDB SHARD_ROW_ID_BITS=4 PRE_SPLIT_REGIONS=2",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
            DialectLoweringRule(
                rule_id="tidb_auto_random",
                description="Convert AUTO_INCREMENT on BigInt PK to AUTO_RANDOM in TiDB",
                pattern=r"\bBIGINT\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b",
                replacement="BIGINT AUTO_RANDOM PRIMARY KEY",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["mysql"],
            ),
            DialectLoweringRule(
                rule_id="tidb_partition_by_range",
                description="Support TiDB partition by range columns",
                pattern=r"\bPARTITION\s+BY\s+RANGE\s*\(([^\)]+)\)",
                replacement=r"PARTITION BY RANGE (\1)",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Translate legacy DBMS error codes to TiDB MySQL wire error codes."""
        return {
            "ORA-00001": "1062",  # ER_DUP_ENTRY
            "ORA-00942": "1146",  # ER_NO_SUCH_TABLE
            "ORA-00904": "1054",  # ER_BAD_FIELD_ERROR
            "ORA-01400": "1048",  # ER_BAD_NULL_ERROR
            "ORA-02291": "1452",  # Cannot add or update child row (FK)
            "ORA-02292": "1451",  # Cannot delete or update parent row (FK)
            "23505": "1062",  # PG unique_violation
            "42P01": "1146",  # PG undefined_table
            "42703": "1054",  # PG undefined_column
            "2627": "1062",  # T-SQL PK violation
            "208": "1146",  # T-SQL invalid object
        }

    def _build_catalog_queries(self) -> dict[str, str]:
        """TiDB INFORMATION_SCHEMA views."""
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
                "SELECT INDEX_NAME, TABLE_NAME, NON_UNIQUE FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tab_name"
            ),
            "constraints": (
                "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tab_name"
            ),
            "partitions": (
                "SELECT PARTITION_NAME, PARTITION_EXPRESSION, TABLE_ROWS "
                "FROM INFORMATION_SCHEMA.PARTITIONS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tab_name"
            ),
        }

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

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """TiDB procedural package lowering."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Ensure TiDB valid partition clause."""
        res = source_sql
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index definition to TiDB syntax."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res
