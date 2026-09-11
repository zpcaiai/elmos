"""openGauss dialect lowering implementation.

Provides comprehensive lowering for:
- DDL: table creation with `DISTRIBUTE BY HASH(...)` (based on primary key or first column),
  storage attributes `WITH (ORIENTATION = ROW/COLUMN)`.
- Types: SERIAL/BIGSERIAL, BYTEA, TEXT, NUMERIC, TIMESTAMPTZ, JSONB, and conversions
  from Oracle (NUMBER, VARCHAR2, CLOB, BLOB), MySQL (AUTO_INCREMENT, TINYINT, DATETIME),
  and T-SQL (IDENTITY, UNIQUEIDENTIFIER, etc.).
- Modes: PG mode (PostgreSQL compatible), A mode (Oracle compatible), B mode (MySQL compatible).
- Functions & Procedures: CREATE OR REPLACE FUNCTION/PROCEDURE ... AS $$ ... $$ LANGUAGE plpgsql.
"""

from __future__ import annotations

import re
from enum import Enum


class OpenGaussMode(str, Enum):
    """openGauss compatibility modes."""

    PG = "PG"  # PostgreSQL compatibility (default)
    A = "A"  # Oracle compatibility mode
    B = "B"  # MySQL compatibility mode


class OpenGaussDialectLowerer:
    """Dedicated SQL dialect lowerer for openGauss / MogDB."""

    def __init__(self, mode: OpenGaussMode = OpenGaussMode.PG) -> None:
        self.mode = mode

    # -------------------------------------------------------------------------
    # DDL & Data Type Lowering
    # -------------------------------------------------------------------------

    def lower_data_types(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower data types from other engines to native openGauss equivalents."""
        res = sql

        # MySQL to openGauss
        # AUTO_INCREMENT -> SERIAL
        res = re.sub(
            r"\bBIGINT\s+AUTO_INCREMENT\b",
            "BIGSERIAL",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(
            r"\bINT\s+AUTO_INCREMENT\b",
            "SERIAL",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(r"\bAUTO_INCREMENT\b", "SERIAL", res, flags=re.IGNORECASE)

        # MySQL text / blob
        res = re.sub(r"\bLONGTEXT\b", "TEXT", res, flags=re.IGNORECASE)
        res = re.sub(r"\bMEDIUMTEXT\b", "TEXT", res, flags=re.IGNORECASE)
        res = re.sub(r"\bTINYTEXT\b", "VARCHAR(255)", res, flags=re.IGNORECASE)
        res = re.sub(r"\bLONGBLOB\b", "BYTEA", res, flags=re.IGNORECASE)
        res = re.sub(r"\bMEDIUMBLOB\b", "BYTEA", res, flags=re.IGNORECASE)
        res = re.sub(r"\bTINYBLOB\b", "BYTEA", res, flags=re.IGNORECASE)
        res = re.sub(r"\bBLOB\b", "BYTEA", res, flags=re.IGNORECASE)
        res = re.sub(r"\bDATETIME\b", "TIMESTAMP", res, flags=re.IGNORECASE)
        res = re.sub(r"\bDOUBLE\b", "DOUBLE PRECISION", res, flags=re.IGNORECASE)
        res = re.sub(r"\bTINYINT\b", "SMALLINT", res, flags=re.IGNORECASE)

        # Oracle to openGauss (unless in mode A where some Oracle types can stay)
        if self.mode != OpenGaussMode.A:
            res = re.sub(r"\bVARCHAR2\b", "VARCHAR", res, flags=re.IGNORECASE)
            res = re.sub(r"\bNVARCHAR2\b", "VARCHAR", res, flags=re.IGNORECASE)
            res = re.sub(r"\bNUMBER\b", "NUMERIC", res, flags=re.IGNORECASE)
            res = re.sub(r"\bCLOB\b", "TEXT", res, flags=re.IGNORECASE)
            res = re.sub(r"\bNCLOB\b", "TEXT", res, flags=re.IGNORECASE)
            res = re.sub(r"\bRAW\b", "BYTEA", res, flags=re.IGNORECASE)
            res = re.sub(r"\bBINARY_DOUBLE\b", "DOUBLE PRECISION", res, flags=re.IGNORECASE)
            res = re.sub(r"\bBINARY_FLOAT\b", "REAL", res, flags=re.IGNORECASE)

        # T-SQL to openGauss
        res = re.sub(
            r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
            "SERIAL",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(r"\bDATETIME2\b", "TIMESTAMP", res, flags=re.IGNORECASE)
        res = re.sub(r"\bNVARCHAR\s*\(\s*MAX\s*\)", "TEXT", res, flags=re.IGNORECASE)
        res = re.sub(r"\bVARCHAR\s*\(\s*MAX\s*\)", "TEXT", res, flags=re.IGNORECASE)
        res = re.sub(r"\bVARBINARY\s*\(\s*MAX\s*\)", "BYTEA", res, flags=re.IGNORECASE)
        res = re.sub(r"\bIMAGE\b", "BYTEA", res, flags=re.IGNORECASE)
        res = re.sub(r"\bUNIQUEIDENTIFIER\b", "UUID", res, flags=re.IGNORECASE)
        res = re.sub(r"\bBIT\b", "BOOLEAN", res, flags=re.IGNORECASE)

        return res

    def extract_distribution_key(self, sql: str) -> str:
        """Detect primary key or first column to use as openGauss hash distribution key."""
        # Check table-level PRIMARY KEY (col1, col2, ...)
        pk_match = re.search(r"\bPRIMARY\s+KEY\s*\(([^\)]+)\)", sql, flags=re.IGNORECASE)
        if pk_match:
            cols = [c.strip().strip('"').strip("`") for c in pk_match.group(1).split(",")]
            if cols:
                return ", ".join(cols)

        # Check column-level PRIMARY KEY: col TYPE ... PRIMARY KEY
        col_pk_match = re.search(
            r"[,\(]\s*([a-zA-Z0-9_\"\`]+)\s+[a-zA-Z0-9_\(\)]+[^,\)]*?\bPRIMARY\s+KEY\b",
            sql,
            flags=re.IGNORECASE,
        )
        if col_pk_match:
            return col_pk_match.group(1).strip().strip('"').strip("`")

        # Fallback: extract the very first column declared in the column list
        first_col_match = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_\.\"\`]+)\s*\(\s*([a-zA-Z0-9_\"\`]+)",
            sql,
            flags=re.IGNORECASE,
        )
        if first_col_match:
            return first_col_match.group(2).strip().strip('"').strip("`")

        return "id"

    def lower_ddl(
        self,
        sql: str,
        source_dialect: str = "postgres",
        orientation: str = "ROW",
        distribute_by: str | None = None,
    ) -> str:
        """Lower table creation DDL to openGauss with orientation and distribution attributes.

        :param sql: Source CREATE TABLE statement
        :param source_dialect: Dialect of origin ('postgres', 'mysql', 'oracle', 'tsql')
        :param orientation: 'ROW' or 'COLUMN'
        :param distribute_by: Explicit column(s) for DISTRIBUTE BY HASH, or auto-detected if None
        """
        cleaned = sql.strip().rstrip(";")

        # Convert data types
        cleaned = self.lower_data_types(cleaned, source_dialect)

        # Normalize quotes: `col` -> "col", [col] -> "col"
        cleaned = re.sub(r"\[([a-zA-Z0-9_]+)\]", r'"\1"', cleaned)
        cleaned = re.sub(r"`([a-zA-Z0-9_]+)`", r'"\1"', cleaned)

        # Determine distribution key
        dist_key = distribute_by if distribute_by else self.extract_distribution_key(cleaned)

        # Strip any existing WITH (...) or DISTRIBUTE BY ... clauses before re-adding
        cleaned = re.sub(r"\s+WITH\s*\([^\)]*\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+DISTRIBUTE\s+BY\s+[^\;]+", "", cleaned, flags=re.IGNORECASE)

        orientation_clause = f"WITH (ORIENTATION = {orientation.upper()})"
        distribute_clause = f"DISTRIBUTE BY HASH({dist_key})"

        return f"{cleaned.strip()} {orientation_clause} {distribute_clause};"

    # -------------------------------------------------------------------------
    # DML & Query Lowering
    # -------------------------------------------------------------------------

    def lower_query(
        self,
        sql: str,
        source_dialect: str = "postgres",
        mode: str | OpenGaussMode | None = None,
    ) -> str:
        """Lower SELECT/DML queries to openGauss in specified compatibility mode."""
        active_mode = OpenGaussMode(mode) if mode else self.mode
        res = sql

        # Limit/Offset standardization
        res = re.sub(
            r"\bOFFSET\s+(\d+)\s+ROWS\s+FETCH\s+(?:FIRST|NEXT)\s+(\d+)\s+ROWS\s+ONLY\b",
            r"LIMIT \2 OFFSET \1",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(
            r"\bLIMIT\s+(\d+)\s*,\s*(\d+)\b",
            r"LIMIT \2 OFFSET \1",
            res,
            flags=re.IGNORECASE,
        )

        if active_mode == OpenGaussMode.PG:
            # PG mode: strip Oracle DUAL table reference
            res = re.sub(r"\s+FROM\s+DUAL\b", "", res, flags=re.IGNORECASE)
            # Function mappings to Postgres equivalents
            res = re.sub(r"\bNVL\s*\(", "COALESCE(", res, flags=re.IGNORECASE)
            res = re.sub(r"\bIFNULL\s*\(", "COALESCE(", res, flags=re.IGNORECASE)
            res = re.sub(r"\bISNULL\s*\(", "COALESCE(", res, flags=re.IGNORECASE)
            res = re.sub(r"\bSYSDATE\b", "CURRENT_TIMESTAMP", res, flags=re.IGNORECASE)
            res = re.sub(r"\bNOW\s*\(\s*\)", "CURRENT_TIMESTAMP", res, flags=re.IGNORECASE)
            res = re.sub(
                r"\b(UUID|NEWID)\s*\(\s*\)",
                "gen_random_uuid()",
                res,
                flags=re.IGNORECASE,
            )
            # GROUP_CONCAT to STRING_AGG
            res = re.sub(
                r"\bGROUP_CONCAT\s*\(\s*([^,\)]+)\s*(?:SEPARATOR\s*'([^']+)')?\s*\)",
                r"STRING_AGG(\1, COALESCE('\2', ','))",
                res,
                flags=re.IGNORECASE,
            )
        elif active_mode == OpenGaussMode.A:
            # A mode (Oracle compatibility):
            # openGauss natively supports DUAL, ROWNUM, NVL, SYSDATE in A mode!
            # Ensure sequence .NEXTVAL is supported natively or mapped
            pass
        elif active_mode == OpenGaussMode.B:
            # B mode (MySQL compatibility):
            # openGauss natively supports IFNULL, NOW, etc. in B mode!
            pass

        return res

    # -------------------------------------------------------------------------
    # Routines: Functions and Procedures
    # -------------------------------------------------------------------------

    def lower_function(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower function declaration to openGauss `$$` envelope with `LANGUAGE plpgsql;`."""
        res = self.lower_data_types(sql, source_dialect)

        # If already has $$ ... $$ LANGUAGE plpgsql, return formatted
        if "$$" in res:
            return res.strip()

        # Parse function signature:
        # CREATE [OR REPLACE] FUNCTION name(args) RETURNS return_type [AS|IS] ... BEGIN ... END;
        pattern = (
            r"(CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION\s+[^\(]+\([^\)]*\))\s+"
            r"(?:RETURNS?|RETURN)\s+([a-zA-Z0-9_\(\)]+)\s*"
            r"(?:AS|IS)?\s*(.*?)\bBEGIN\b(.*?)\bEND\s*;?$"
        )
        match = re.search(pattern, res.strip(), flags=re.DOTALL | re.IGNORECASE)
        if match:
            header = match.group(1).strip()
            ret_type = match.group(2).strip()
            decl = match.group(3).strip()
            body = match.group(4).strip()

            # Clean parameter declarations: T-SQL @var -> var, Oracle var IN type -> var type
            header = re.sub(r"@([a-zA-Z0-9_]+)", r"\1", header)
            header = re.sub(r"\b([a-zA-Z0-9_]+)\s+IN\s+", r"\1 ", header, flags=re.IGNORECASE)

            # Clean DECLARE section
            decl_block = f"DECLARE\n    {decl}\n" if decl else ""

            # Ensure CREATE OR REPLACE
            header = re.sub(r"^CREATE\s+FUNCTION\b", "CREATE OR REPLACE FUNCTION", header, flags=re.IGNORECASE)

            return (
                f"{header} RETURNS {ret_type}\n"
                f"AS $$\n"
                f"{decl_block}"
                f"BEGIN\n"
                f"    {body}\n"
                f"END;\n"
                f"$$ LANGUAGE plpgsql;"
            )

        # If pattern did not match full structure, ensure CREATE OR REPLACE and plpgsql
        if not re.search(r"\bLANGUAGE\s+plpgsql\b", res, flags=re.IGNORECASE):
            res = res.strip().rstrip(";") + " LANGUAGE plpgsql;"
        return res

    def lower_procedure(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower procedure declaration to openGauss `$$` envelope with `LANGUAGE plpgsql;`."""
        res = self.lower_data_types(sql, source_dialect)

        if "$$" in res:
            return res.strip()

        # Match procedure: CREATE [OR REPLACE] PROCEDURE name(...) [AS|IS] ... BEGIN ... END;
        pattern = (
            r"(CREATE(?:\s+OR\s+REPLACE)?\s+PROCEDURE\s+[^\(]+(?:\([^\)]*\))?)\s*"
            r"(?:AS|IS)?\s*(.*?)\bBEGIN\b(.*?)\bEND\s*;?$"
        )
        match = re.search(pattern, res.strip(), flags=re.DOTALL | re.IGNORECASE)
        if match:
            header = match.group(1).strip()
            decl = match.group(2).strip()
            body = match.group(3).strip()

            # Clean parameter declarations
            header = re.sub(r"@([a-zA-Z0-9_]+)", r"\1", header)
            header = re.sub(r"\b([a-zA-Z0-9_]+)\s+IN\s+", r"\1 ", header, flags=re.IGNORECASE)

            decl_block = f"DECLARE\n    {decl}\n" if decl else ""
            header = re.sub(r"^CREATE\s+PROCEDURE\b", "CREATE OR REPLACE PROCEDURE", header, flags=re.IGNORECASE)

            return (
                f"{header}\n"
                f"AS $$\n"
                f"{decl_block}"
                f"BEGIN\n"
                f"    {body}\n"
                f"END;\n"
                f"$$ LANGUAGE plpgsql;"
            )

        if not re.search(r"\bLANGUAGE\s+plpgsql\b", res, flags=re.IGNORECASE):
            res = res.strip().rstrip(";") + " LANGUAGE plpgsql;"
        return res

    def lower_create_table(
        self,
        sql: str,
        source_dialect: str = "postgres",
        orientation: str = "ROW",
        distribute_column: str | None = None,
    ) -> str:
        """Alias for lower_ddl."""
        return self.lower_ddl(
            sql,
            source_dialect=source_dialect,
            orientation=orientation,
            distribute_by=distribute_column,
        )

    def lower_routine(
        self,
        sql: str,
        source_dialect: str = "postgres",
        routine_type: str | None = None,
    ) -> str:
        """Lower function or procedure to openGauss plpgsql format."""
        target_kind = (routine_type or "").upper().strip()
        if target_kind == "PROCEDURE":
            return self.lower_procedure(sql, source_dialect)
        if target_kind == "FUNCTION":
            return self.lower_function(sql, source_dialect)
        if re.search(r"\bFUNCTION\b", sql, flags=re.IGNORECASE):
            return self.lower_function(sql, source_dialect)
        return self.lower_procedure(sql, source_dialect)


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------

_DEFAULT_LOWERER = OpenGaussDialectLowerer()


def lower_opengauss_ddl(
    sql: str,
    source_dialect: str = "postgres",
    orientation: str = "ROW",
    distribute_by: str | None = None,
) -> str:
    """Lower DDL statement to openGauss with ORIENTATION and DISTRIBUTE BY attributes."""
    return _DEFAULT_LOWERER.lower_ddl(
        sql,
        source_dialect=source_dialect,
        orientation=orientation,
        distribute_by=distribute_by,
    )


def lower_opengauss_query(
    sql: str,
    source_dialect: str = "postgres",
    mode: str = "PG",
) -> str:
    """Lower query to openGauss under specified compatibility mode."""
    return _DEFAULT_LOWERER.lower_query(sql, source_dialect=source_dialect, mode=mode)


def lower_opengauss_routine(sql: str, source_dialect: str = "postgres") -> str:
    """Lower function or procedure to openGauss plpgsql envelope."""
    return _DEFAULT_LOWERER.lower_routine(sql, source_dialect=source_dialect)
