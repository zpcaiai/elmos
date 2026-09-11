"""Dameng (DM8) dialect lowering implementation.

Provides comprehensive lowering for:
- DDL: table creation, column type mappings (SERIAL/AUTO_INCREMENT -> IDENTITY(1,1),
  BOOLEAN -> BIT, TEXT -> CLOB, BYTEA/BLOB -> BLOB, VARCHAR(n), etc.), constraints (PK, FK, UNIQUE, CHECK).
- Sequences: CREATE SEQUENCE, seq.NEXTVAL, NEXTVAL('seq').
- DML/Query lowering: LIMIT/OFFSET standardizing, DUAL table support, functions
  (NOW() -> SYSDATE, IFNULL -> NVL, ILIKE -> REGEXP_LIKE or LOWER() LIKE LOWER(), INSTR, SUBSTR, DECODE).
- Upsert lowering: MySQL ON DUPLICATE KEY UPDATE / Postgres ON CONFLICT -> DM8 MERGE INTO.
"""

from __future__ import annotations

import re


class DM8DialectLowerer:
    """Dedicated SQL dialect lowerer for Dameng 8 (DM8)."""

    def __init__(self, ilike_strategy: str = "regexp_like") -> None:
        """Initialize lowerer.

        :param ilike_strategy: 'regexp_like' for REGEXP_LIKE(col, pat, 'i')
                               or 'lower' for LOWER(col) LIKE LOWER(pat)
        """
        self.ilike_strategy = ilike_strategy

    # -------------------------------------------------------------------------
    # DDL Lowering
    # -------------------------------------------------------------------------

    def lower_data_types(self, sql: str, source_dialect: str = "postgres") -> str:
        """Map data types from source dialect to DM8 equivalents."""
        res = sql

        # Serial / Identity mappings
        # Postgres: BIGSERIAL -> BIGINT IDENTITY(1, 1), SERIAL -> INT IDENTITY(1, 1)
        res = re.sub(r"\bBIGSERIAL\b", "BIGINT IDENTITY(1, 1)", res, flags=re.IGNORECASE)
        res = re.sub(r"\bSERIAL\b", "INT IDENTITY(1, 1)", res, flags=re.IGNORECASE)
        # Postgres GENERATED ... AS IDENTITY
        res = re.sub(
            r"\bGENERATED\s+BY\s+DEFAULT\s+AS\s+IDENTITY\b",
            "IDENTITY(1, 1)",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(
            r"\bGENERATED\s+ALWAYS\s+AS\s+IDENTITY\b",
            "IDENTITY(1, 1)",
            res,
            flags=re.IGNORECASE,
        )
        # MySQL AUTO_INCREMENT -> IDENTITY(1, 1)
        res = re.sub(r"\bAUTO_INCREMENT\b", "IDENTITY(1, 1)", res, flags=re.IGNORECASE)
        # T-SQL IDENTITY with parameters: IDENTITY(1,1) -> IDENTITY(1, 1)
        res = re.sub(
            r"\bIDENTITY\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)",
            r"IDENTITY(\1, \2)",
            res,
            flags=re.IGNORECASE,
        )

        # Boolean: DM8 uses BIT for BOOLEAN
        res = re.sub(r"\bBOOLEAN\b", "BIT", res, flags=re.IGNORECASE)
        res = re.sub(r"\bBOOL\b", "BIT", res, flags=re.IGNORECASE)
        # Defaults for boolean
        res = re.sub(r"\bDEFAULT\s+TRUE\b", "DEFAULT 1", res, flags=re.IGNORECASE)
        res = re.sub(r"\bDEFAULT\s+FALSE\b", "DEFAULT 0", res, flags=re.IGNORECASE)

        # Text types -> CLOB
        res = re.sub(r"\bLONGTEXT\b", "CLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bMEDIUMTEXT\b", "CLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bTEXT\b", "CLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bNVARCHAR\s*\(\s*MAX\s*\)", "CLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bVARCHAR\s*\(\s*MAX\s*\)", "CLOB", res, flags=re.IGNORECASE)

        # Binary types -> BLOB
        res = re.sub(r"\bBYTEA\b", "BLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bLONGBLOB\b", "BLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bMEDIUMBLOB\b", "BLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bVARBINARY\s*\(\s*MAX\s*\)", "BLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bIMAGE\b", "BLOB", res, flags=re.IGNORECASE)

        # JSON / JSONB -> CLOB
        res = re.sub(r"\bJSONB\b", "CLOB", res, flags=re.IGNORECASE)
        res = re.sub(r"\bJSON\b", "CLOB", res, flags=re.IGNORECASE)

        # Timestamps and Dates
        res = re.sub(
            r"\bTIMESTAMPTZ\b",
            "TIMESTAMP WITH TIME ZONE",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(r"\bDATETIME2\b", "TIMESTAMP", res, flags=re.IGNORECASE)
        res = re.sub(r"\bDATETIME\b", "TIMESTAMP", res, flags=re.IGNORECASE)

        # UUID -> VARCHAR(36)
        res = re.sub(r"\bUUID\b", "VARCHAR(36)", res, flags=re.IGNORECASE)
        res = re.sub(r"\bUNIQUEIDENTIFIER\b", "VARCHAR(36)", res, flags=re.IGNORECASE)

        # Double precision -> DOUBLE
        res = re.sub(r"\bDOUBLE\s+PRECISION\b", "DOUBLE", res, flags=re.IGNORECASE)

        # Default current timestamp -> SYSDATE
        res = re.sub(
            r"\bDEFAULT\s+CURRENT_TIMESTAMP\b",
            "DEFAULT SYSDATE",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(
            r"\bDEFAULT\s+NOW\s*\(\s*\)",
            "DEFAULT SYSDATE",
            res,
            flags=re.IGNORECASE,
        )

        return res

    def lower_ddl(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower DDL statements (CREATE TABLE, constraints, etc.) for DM8."""
        cleaned = sql.strip()

        # Remove PostgreSQL schema/extension-specific syntax if any
        cleaned = re.sub(r"\bIF\s+NOT\s+EXISTS\b", "", cleaned, flags=re.IGNORECASE)
        # Collapse multi spaces caused by IF NOT EXISTS removal
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        # Apply data type lowering
        cleaned = self.lower_data_types(cleaned, source_dialect)

        # Normalize square brackets [col] -> "col" if coming from T-SQL
        cleaned = re.sub(r"\[([a-zA-Z0-9_]+)\]", r'"\1"', cleaned)

        # Backticks `col` -> "col" if coming from MySQL
        cleaned = re.sub(r"`([a-zA-Z0-9_]+)`", r'"\1"', cleaned)

        return cleaned

    # -------------------------------------------------------------------------
    # Sequence Lowering
    # -------------------------------------------------------------------------

    def lower_sequence(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower sequence creation and usage."""
        res = sql.strip()

        # Postgres NEXTVAL('seq') or nextval('schema.seq') -> seq.NEXTVAL
        res = re.sub(
            r"\bNEXTVAL\s*\(\s*['\"]([a-zA-Z0-9_\.]+)['\"]\s*\)",
            r"\1.NEXTVAL",
            res,
            flags=re.IGNORECASE,
        )
        # Postgres CURRVAL('seq') -> seq.CURRVAL
        res = re.sub(
            r"\bCURRVAL\s*\(\s*['\"]([a-zA-Z0-9_\.]+)['\"]\s*\)",
            r"\1.CURRVAL",
            res,
            flags=re.IGNORECASE,
        )
        # Normalize dot-notation nextval/currval to uppercase
        res = re.sub(r"\.nextval\b", ".NEXTVAL", res, flags=re.IGNORECASE)
        res = re.sub(r"\.currval\b", ".CURRVAL", res, flags=re.IGNORECASE)

        # CREATE SEQUENCE cleaning
        res = re.sub(r"\bIF\s+NOT\s+EXISTS\b", "", res, flags=re.IGNORECASE)
        res = re.sub(r"[ \t]+", " ", res)
        return res

    # -------------------------------------------------------------------------
    # DML / Query Lowering
    # -------------------------------------------------------------------------

    def lower_functions(self, sql: str) -> str:
        """Lower built-in functions to DM8 equivalents."""
        res = sql

        # NOW() -> SYSDATE
        res = re.sub(r"\bNOW\s*\(\s*\)", "SYSDATE", res, flags=re.IGNORECASE)

        # CURRENT_TIMESTAMP -> SYSTIMESTAMP (when used as function/keyword in DML)
        res = re.sub(r"\bCURRENT_TIMESTAMP\b", "SYSTIMESTAMP", res, flags=re.IGNORECASE)

        # IFNULL(a, b) -> NVL(a, b)
        res = re.sub(r"\bIFNULL\s*\(", "NVL(", res, flags=re.IGNORECASE)

        # ISNULL(a, b) -> NVL(a, b)
        res = re.sub(r"\bISNULL\s*\(", "NVL(", res, flags=re.IGNORECASE)

        # ILIKE: col ILIKE 'pattern'
        if self.ilike_strategy == "lower":
            res = re.sub(
                r"([a-zA-Z0-9_\.\"]+)\s+ILIKE\s+('[^']+'|[a-zA-Z0-9_\.\"]+)",
                r"LOWER(\1) LIKE LOWER(\2)",
                res,
                flags=re.IGNORECASE,
            )
        else:
            res = re.sub(
                r"([a-zA-Z0-9_\.\"]+)\s+ILIKE\s+('[^']+')",
                r"REGEXP_LIKE(\1, \2, 'i')",
                res,
                flags=re.IGNORECASE,
            )

        # SUBSTRING(str, pos, len) or SUBSTRING(str FROM pos FOR len) -> SUBSTR(...)
        res = re.sub(
            r"\bSUBSTRING\s*\(\s*([^,]+?)\s+FROM\s+(\d+)\s+FOR\s+(\d+)\s*\)",
            r"SUBSTR(\1, \2, \3)",
            res,
            flags=re.IGNORECASE,
        )
        res = re.sub(
            r"\bSUBSTRING\s*\(",
            "SUBSTR(",
            res,
            flags=re.IGNORECASE,
        )

        # UUID generators
        res = re.sub(
            r"\b(GEN_RANDOM_UUID|UUID|NEWID)\s*\(\s*\)",
            "RAWTOHEX(SYS_GUID())",
            res,
            flags=re.IGNORECASE,
        )

        # INSTR and DECODE: already valid DM8 native syntax!

        return res

    def lower_limit_offset(self, sql: str) -> str:
        """Lower LIMIT/OFFSET clauses to DM8 standard `LIMIT count OFFSET offset`."""
        res = sql

        # ANSI standard: OFFSET n ROWS FETCH NEXT m ROWS ONLY -> LIMIT m OFFSET n
        res = re.sub(
            r"\bOFFSET\s+(\d+)\s+ROWS\s+FETCH\s+(?:FIRST|NEXT)\s+(\d+)\s+ROWS\s+ONLY\b",
            r"LIMIT \2 OFFSET \1",
            res,
            flags=re.IGNORECASE,
        )

        # MySQL LIMIT offset, count -> LIMIT count OFFSET offset
        res = re.sub(
            r"\bLIMIT\s+(\d+)\s*,\s*(\d+)\b",
            r"LIMIT \2 OFFSET \1",
            res,
            flags=re.IGNORECASE,
        )

        # T-SQL SELECT TOP n ... -> SELECT ... LIMIT n
        top_match = re.search(r"\bSELECT\s+TOP\s+(\d+)\s+(.+)", res, flags=re.IGNORECASE | re.DOTALL)
        if top_match:
            top_count = top_match.group(1)
            rest_of_query = top_match.group(2).rstrip(";")
            if "LIMIT" not in rest_of_query.upper():
                res = f"SELECT {rest_of_query} LIMIT {top_count}"

        return res

    def ensure_dual_table(self, sql: str) -> str:
        """Ensure constant/expression-only SELECT queries have FROM DUAL for DM8."""
        stripped = sql.strip()
        semicolon = ";" if stripped.endswith(";") else ""
        query = stripped.rstrip(";").strip()

        # If it's a SELECT and doesn't contain FROM, add FROM DUAL
        select_match = re.match(r"^SELECT\s+(.+)$", query, flags=re.IGNORECASE | re.DOTALL)
        if select_match:
            body = select_match.group(1)
            # Check if FROM exists as a standalone SQL keyword
            if not re.search(r"\bFROM\b", body, flags=re.IGNORECASE):
                query = f"SELECT {body} FROM DUAL"  # noqa: S608

        return f"{query}{semicolon}"

    def lower_query(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower complete SELECT query to DM8."""
        res = sql
        res = self.lower_functions(res)
        res = self.lower_sequence(res, source_dialect)
        res = self.lower_limit_offset(res)
        res = self.ensure_dual_table(res)
        return res

    def wrap_with_rownum(self, query: str, limit: int, offset: int = 0) -> str:
        """Wrap query using DM8 / Oracle ROWNUM pagination pattern."""
        clean = query.strip().rstrip(";")
        if offset > 0:
            max_r = offset + limit
            return (
                f"SELECT * FROM (SELECT inner_query.*, ROWNUM AS rnum FROM ({clean}) inner_query "  # noqa: S608
                f"WHERE ROWNUM <= {max_r}) WHERE rnum > {offset};"
            )
        return f"SELECT * FROM ({clean}) WHERE ROWNUM <= {limit};"  # noqa: S608

    # -------------------------------------------------------------------------
    # Upsert Lowering (MERGE INTO)
    # -------------------------------------------------------------------------

    def lower_upsert(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower MySQL ON DUPLICATE KEY UPDATE / Postgres ON CONFLICT to DM8 MERGE INTO."""
        cleaned = sql.strip().rstrip(";")

        # Try matching PostgreSQL:
        # INSERT INTO table (col1, col2, ...) VALUES (val1, val2, ...)
        # ON CONFLICT (pk1, ...) DO UPDATE SET col2 = EXCLUDED.col2, ...
        # OR ON CONFLICT (pk1, ...) DO NOTHING
        pg_pattern = (
            r"INSERT\s+INTO\s+([a-zA-Z0-9_\.\"]+)\s*\((.*?)\)\s*"
            r"VALUES\s*\((.*?)\)\s*"
            r"ON\s+CONFLICT\s*(?:\((.*?)\))?\s*"
            r"(DO\s+NOTHING|DO\s+UPDATE\s+SET\s+(.*?))$"
        )
        pg_match = re.search(pg_pattern, cleaned, flags=re.IGNORECASE | re.DOTALL)
        if pg_match:
            table = pg_match.group(1).strip()
            cols = [c.strip() for c in pg_match.group(2).split(",")]
            vals = [v.strip() for v in self._split_csv(pg_match.group(3))]
            pk_cols_str = pg_match.group(4)
            conflict_action = pg_match.group(5).strip()

            pk_cols = [c.strip() for c in pk_cols_str.split(",")] if pk_cols_str else [cols[0]]

            # Build source subquery: SELECT val1 AS col1, val2 AS col2, ... FROM DUAL
            src_select_parts = [f"{val} AS {col}" for col, val in zip(cols, vals, strict=False)]
            src_subquery = f"SELECT {', '.join(src_select_parts)} FROM DUAL"  # noqa: S608

            # ON condition: ON (table.pk1 = src.pk1 AND ...)
            on_conds = [f"{table}.{pk} = src.{pk}" for pk in pk_cols]
            on_clause = " AND ".join(on_conds)

            # WHEN NOT MATCHED THEN INSERT (cols) VALUES (src.cols)
            src_cols_str = ", ".join(f"src.{c}" for c in cols)
            insert_clause = (
                f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({src_cols_str})"  # noqa: S608
            )

            if re.match(r"^DO\s+NOTHING$", conflict_action, flags=re.IGNORECASE):
                return (  # noqa: S608
                    f"MERGE INTO {table} USING ({src_subquery}) src "
                    f"ON ({on_clause}) "
                    f"{insert_clause};"
                )

            # DO UPDATE SET col2 = EXCLUDED.col2, ...
            set_clause = pg_match.group(6).strip()
            # Replace EXCLUDED.col with src.col
            dm8_set_clause = re.sub(
                r"\bEXCLUDED\.([a-zA-Z0-9_]+)\b",
                r"src.\1",
                set_clause,
                flags=re.IGNORECASE,
            )
            update_clause = f"WHEN MATCHED THEN UPDATE SET {dm8_set_clause}"

            return (  # noqa: S608
                f"MERGE INTO {table} USING ({src_subquery}) src "
                f"ON ({on_clause}) "
                f"{update_clause} "
                f"{insert_clause};"
            )

        # Try matching MySQL:
        # INSERT INTO table (col1, col2, ...) VALUES (val1, val2, ...)
        # ON DUPLICATE KEY UPDATE col2 = val2, ...
        mysql_pattern = (
            r"INSERT\s+INTO\s+([a-zA-Z0-9_\.\"]+)\s*\((.*?)\)\s*"
            r"VALUES\s*\((.*?)\)\s*"
            r"ON\s+DUPLICATE\s+KEY\s+UPDATE\s+(.*?)$"
        )
        mysql_match = re.search(mysql_pattern, cleaned, flags=re.IGNORECASE | re.DOTALL)
        if mysql_match:
            table = mysql_match.group(1).strip()
            cols = [c.strip() for c in mysql_match.group(2).split(",")]
            vals = [v.strip() for v in self._split_csv(mysql_match.group(3))]
            set_clause = mysql_match.group(4).strip()

            # For MySQL, first column is commonly primary key if unspecified
            pk_cols = [cols[0]]

            src_select_parts = [f"{val} AS {col}" for col, val in zip(cols, vals, strict=False)]
            src_subquery = f"SELECT {', '.join(src_select_parts)} FROM DUAL"  # noqa: S608

            on_conds = [f"{table}.{pk} = src.{pk}" for pk in pk_cols]
            on_clause = " AND ".join(on_conds)

            # In MySQL ON DUPLICATE KEY UPDATE col = VALUES(col) -> src.col
            dm8_set_clause = re.sub(
                r"\bVALUES\s*\(\s*([a-zA-Z0-9_]+)\s*\)",
                r"src.\1",
                set_clause,
                flags=re.IGNORECASE,
            )

            src_vals_str = ", ".join(f"src.{c}" for c in cols)
            insert_clause = (
                f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({src_vals_str})"  # noqa: S608
            )
            update_clause = f"WHEN MATCHED THEN UPDATE SET {dm8_set_clause}"

            return (  # noqa: S608
                f"MERGE INTO {table} USING ({src_subquery}) src "
                f"ON ({on_clause}) "
                f"{update_clause} "
                f"{insert_clause};"
            )

        # Fallback: if not an upsert pattern, return as-is
        return sql

    @staticmethod
    def _split_csv(text: str) -> list[str]:
        """Split a comma-separated list of values respecting quotes and parens."""
        parts = []
        current: list[str] = []
        depth = 0
        in_str = False
        str_char = ""

        for char in text:
            if in_str:
                current.append(char)
                if char == str_char:
                    in_str = False
            else:
                if char in ("'", '"'):
                    in_str = True
                    str_char = char
                    current.append(char)
                elif char == "(":
                    depth += 1
                    current.append(char)
                elif char == ")":
                    depth -= 1
                    current.append(char)
                elif char == "," and depth == 0:
                    parts.append("".join(current).strip())
                    current = []
                else:
                    current.append(char)

        if current:
            parts.append("".join(current).strip())
        return parts


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------

_DEFAULT_LOWERER = DM8DialectLowerer()


def lower_dm8_ddl(sql: str, source_dialect: str = "postgres") -> str:
    """Lower source DDL to DM8 dialect."""
    return _DEFAULT_LOWERER.lower_ddl(sql, source_dialect=source_dialect)


def lower_dm8_query(sql: str, source_dialect: str = "postgres") -> str:
    """Lower source query to DM8 dialect."""
    return _DEFAULT_LOWERER.lower_query(sql, source_dialect=source_dialect)


def lower_dm8_sequence(sql: str, source_dialect: str = "postgres") -> str:
    """Lower sequence definition or access to DM8 dialect."""
    return _DEFAULT_LOWERER.lower_sequence(sql, source_dialect=source_dialect)


def lower_dm8_upsert(sql: str, source_dialect: str = "postgres") -> str:
    """Lower upsert statements to DM8 MERGE INTO."""
    return _DEFAULT_LOWERER.lower_upsert(sql, source_dialect=source_dialect)
