"""openGauss / MogDB Dedicated Target Lowerer.

openGauss provides enterprise relational capabilities based on an enhanced PL/pgSQL
procedural engine, row/column orientation, distribution keys, and vector execution.
"""

from __future__ import annotations

import re

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)


class OpenGaussTargetLowerer(ChinaDbTargetLowerer):
    """Dedicated lowerer for openGauss and MogDB."""

    target_id = "opengauss"
    display_name = "openGauss / MogDB"
    family = "pg_compat"

    def _build_type_mappings(self) -> dict[str, str]:
        return {
            # Oracle to openGauss
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
            "BFILE": "VARCHAR(256)",
            "ROWID": "VARCHAR(64)",
            # T-SQL to openGauss
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
            # MySQL to openGauss
            "DATETIME": "TIMESTAMP",
            "LONGTEXT": "TEXT",
            "MEDIUMTEXT": "TEXT",
            "TINYTEXT": "VARCHAR(255)",
            "LONGBLOB": "BYTEA",
            "MEDIUMBLOB": "BYTEA",
            "TINYBLOB": "BYTEA",
            "DOUBLE": "DOUBLE PRECISION",
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
            "LOCATE": "INSTR",
            "NEWID": "MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)::UUID",
            "SYS_GUID": "REPLACE(MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT), '-', '')",
            "UUID": "MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)::UUID",
        }

    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        return [
            DialectLoweringRule(
                rule_id="og_dual_removal",
                description="Remove FROM DUAL in openGauss queries",
                pattern=r"\s+FROM\s+DUAL\b",
                replacement="",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
            DialectLoweringRule(
                rule_id="og_square_brackets",
                description="Convert T-SQL [col] to openGauss \"col\"",
                pattern=r"\[([a-zA-Z0-9_]+)\]",
                replacement=r'"\1"',
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="og_variable_prefix",
                description="Convert T-SQL @var to v_var in openGauss",
                pattern=r"@([a-zA-Z0-9_]+)",
                replacement=r"v_\1",
                is_regex=True,
                applies_to_dialects=["tsql", "sqlserver"],
            ),
            DialectLoweringRule(
                rule_id="og_limit_offset",
                description="Standardize LIMIT and OFFSET clauses",
                pattern=r"\bOFFSET\s+(\d+)\s+ROWS\s+FETCH\s+NEXT\s+(\d+)\s+ROWS\s+ONLY",
                replacement=r"LIMIT \2 OFFSET \1",
                is_regex=True,
                flags=re.IGNORECASE,
                applies_to_dialects=["all"],
            ),
        ]

    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower procedure to openGauss PL/pgSQL dialect with $$ envelope."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        if "$$" not in res and "BEGIN" in res.upper():
            m = re.search(
                r"(CREATE(?:\s+OR\s+REPLACE)?\s+PROCEDURE\s+[^\(]+(?:\([^\)]*\))?)\s+(?:AS|IS)\s*(.*)\bBEGIN\b(.*)\bEND\s*;?",
                res,
                re.DOTALL | re.IGNORECASE,
            )
            if m:
                header = m.group(1)
                decl = m.group(2).strip()
                body = m.group(3).strip()
                decl_block = f"DECLARE\n{decl}\n" if decl else ""
                res = f"{header}\nAS $$\n{decl_block}BEGIN\n{body}\nEND;\n$$ LANGUAGE plpgsql;"

        return res

    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower function declaration to openGauss PL/pgSQL."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)

        if "$$" not in res and "BEGIN" in res.upper():
            m = re.search(
                r"(CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION\s+[^\(]+\([^\)]*\)\s+RETURNS?\s+[a-zA-Z0-9_\(\)]+)\s+(?:AS|IS)\s*(.*)\bBEGIN\b(.*)\bEND\s*;?",
                res,
                re.DOTALL | re.IGNORECASE,
            )
            if m:
                header = m.group(1)
                decl = m.group(2).strip()
                body = m.group(3).strip()
                decl_block = f"DECLARE\n{decl}\n" if decl else ""
                res = f"{header}\nAS $$\n{decl_block}BEGIN\n{body}\nEND;\n$$ LANGUAGE plpgsql;"

        return res

    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger to openGauss trigger function + trigger creation."""
        res = self.lower_data_types(source_sql, source_dialect)
        res = self.lower_builtin_functions(res, source_dialect)
        res = self.apply_custom_rules(res, source_dialect)
        res = res.replace(":NEW.", "NEW.")
        res = res.replace(":OLD.", "OLD.")
        return res

    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and references."""
        res = source_sql
        res = re.sub(
            r"\b([a-zA-Z0-9_]+)\.NEXTVAL\b",
            r"NEXTVAL('\1')",
            res,
            flags=re.IGNORECASE,
        )
        return res
