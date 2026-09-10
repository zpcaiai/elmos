"""GBase 8s (Informix-based) Dedicated Target Lowerer.

GBase 8s uses Informix-compatible SPL (Stored Procedure Language), DEFINE / LET syntax,
FIRST / SKIP pagination, and specialized SERIAL / LVARCHAR data types.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class GBase8sTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for GBase 8s."""

    target_id = "gbase8s"
    display_name = "GBase 8s"
    family = "informix_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to GBase 8s
            "VARCHAR2": "VARCHAR",
            "NVARCHAR2": "NVARCHAR",
            "NUMBER": "DECIMAL",
            "CLOB": "TEXT",
            "NCLOB": "TEXT",
            "BLOB": "BYTE",
            "RAW": "BYTE",
            "LONG RAW": "BYTE",
            "LONG": "TEXT",
            "BFILE": "VARCHAR(256)",
            # T-SQL to GBase 8s
            "DATETIME2": "DATETIME YEAR TO FRACTION(5)",
            "SMALLDATETIME": "DATETIME YEAR TO MINUTE",
            "TIMESTAMP": "DATETIME YEAR TO FRACTION(5)",
            "DATE": "DATE",
            "MONEY": "MONEY",
            "SMALLMONEY": "MONEY",
            "BIT": "SMALLINT",
            "IDENTITY": "SERIAL",
            # MySQL to GBase 8s
            "DATETIME": "DATETIME YEAR TO FRACTION(5)",
            "LONGTEXT": "TEXT",
            "LONGBLOB": "BYTE",
            "TINYINT": "SMALLINT",
        }

    def _build_builtin_mappings(self) -> dict[str, str]:
        return {
            "SYSDATE": "CURRENT",
            "GETDATE": "CURRENT",
            "NOW": "CURRENT",
            "ISNULL": "NVL",
            "IFNULL": "NVL",
            "COALESCE": "NVL",
            "LEN": "LENGTH",
            "CHAR_LENGTH": "LENGTH",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="gbase8s_or_replace_strip",
                description="GBase 8s does not support OR REPLACE; use DROP + CREATE",
                pattern=r"\bCREATE\s+OR\s+REPLACE\s+PROCEDURE\b",
                replacement="CREATE PROCEDURE",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gbase8s_assign_let",
                description="Convert variable assignment in SPL to LET var = val",
                pattern=r"^\s*([a-zA-Z0-9_]+)\s*:=\s*(.+);",
                replacement=r"LET \1 = \2;",
                is_regex=True,
                flags=re.MULTILINE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="gbase8s_dual_sysmaster",
                description="GBase 8s DUAL queries map to 'informix'.systables",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement=" FROM 'informix'.systables WHERE tabid = 1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="gbase8s_pagination_first_skip",
                description="Convert LIMIT n OFFSET m to FIRST n SKIP m",
                pattern=r"\bSELECT\s+(.+)\s+LIMIT\s+(\d+)\s+OFFSET\s+(\d+)",
                replacement=r"SELECT SKIP \3 FIRST \2 \1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="gbase8s_on_exception",
                description="Map EXCEPTION block to ON EXCEPTION statement in GBase 8s",
                pattern=r"\bEXCEPTION\s+WHEN\s+OTHERS\s+THEN\b",
                replacement="ON EXCEPTION",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["oracle", "plsql"],
            ),
            DialectLoweringRule(
                rule_id="gbase8s_define_var",
                description="Prefix variable declarations with DEFINE in SPL",
                pattern=r"^\s*v_([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_\(\)]+)\s*;",
                replacement=r"DEFINE v_\1 \2;",
                is_regex=True,
                flags=re.MULTILINE,
                applies_to_dialects=["oracle", "plsql"],
            ),
        ]

    def _build_error_code_mappings(self) -> dict[str, str]:
        """Translate legacy DBMS error codes to GBase 8s / Informix error numbers."""
        return {
            "ORA-00001": "-239",   # Duplicate key in index
            "ORA-00942": "-206",   # Specified table is not in database
            "ORA-00904": "-217",   # Column not found in any table
            "ORA-01400": "-391",   # Cannot insert a null into column
            "ORA-01403": "100",    # No records found
            "23505": "-239",
            "42P01": "-206",
            "42703": "-217",
            "1062": "-239",
            "1146": "-206",
            "2627": "-239",
        }

    def _build_catalog_queries(self) -> dict[str, str]:
        """GBase 8s / Informix systables catalog queries."""
        return {
            "tables": (
                "SELECT tabname AS table_name FROM 'informix'.systables "
                "WHERE tabtype = 'T' AND tabid >= 100 ORDER BY tabname"
            ),
            "columns": (
                "SELECT c.colname, c.coltype, c.collength "
                "FROM 'informix'.syscolumns c JOIN 'informix'.systables t "
                "ON c.tabid = t.tabid WHERE t.tabname = :tab_name ORDER BY c.colno"
            ),
            "indexes": (
                "SELECT idxname AS index_name FROM 'informix'.sysindexes "
                "WHERE tabid = (SELECT tabid FROM 'informix'.systables WHERE tabname = :tab_name)"
            ),
            "procedures": (
                "SELECT procname AS routine_name FROM 'informix'.sysprocedures "
                "WHERE procid >= 1"
            ),
            "constraints": (
                "SELECT constrname AS constraint_name, constrtype AS constraint_type "
                "FROM 'informix'.sysconstraints "
                "WHERE tabid = (SELECT tabid FROM 'informix'.systables WHERE tabname = :tab_name)"
            ),
        }

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to GBase 8s SPL syntax."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        if "END PROCEDURE" not in res.upper():
            res = re.sub(r"\bEND\s*;?$", "END PROCEDURE;", res.strip(), flags=re.IGNORECASE)

        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function to GBase 8s SPL syntax."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        if "END FUNCTION" not in res.upper():
            res = re.sub(r"\bEND\s*;?$", "END FUNCTION;", res.strip(), flags=re.IGNORECASE)
        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to GBase 8s syntax."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval."""
        return source_sql

    def lower_package(self, source_sql: str, source_dialect: str) -> str:
        """GBase 8s splits packages into standalone SPL procedures."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

    def lower_partition_clause(self, source_sql: str, source_dialect: str) -> str:
        """Lower table partitioning to GBase 8s FRAGMENT BY expression."""
        res = source_sql
        res = re.sub(
            r"\bPARTITION\s+BY\s+RANGE\b",
            "FRAGMENT BY EXPRESSION",
            res,
            flags=re.IGNORECASE,
        )
        return res

    def lower_index_definition(self, source_sql: str, source_dialect: str) -> str:
        """Lower index creation to GBase 8s syntax."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        return res

