"""Enterprise SQL Diagnostic Auto-Repairer.

Performs deterministic multi-stage repair on enterprise SQL statements
to reconcile common dialect divergences before and during migration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class RepairResult:
    original_sql: str
    repaired_sql: str
    repairs_applied: list[str] = field(default_factory=list)
    is_modified: bool = False


class SqlDiagnosticAutoRepairer:
    """Multi-stage targeted auto-repairer for enterprise SQL dialect migrations."""

    def __init__(
        self,
        namespace_map: Mapping[str, str] | None = None,
        target_dialect: str = "postgresql",
    ) -> None:
        self.namespace_map = dict(namespace_map) if namespace_map else {}
        self.target_dialect = target_dialect.lower()

    def repair_statement(self, sql: str) -> RepairResult:
        """Apply Stage 1, Stage 2, and Stage 3 repairs to a single SQL statement."""
        current_sql = sql
        repairs: list[str] = []

        # Stage 1: Strip client-specific directives and comments
        stage1_sql, stage1_repairs = self._repair_stage1_directives(current_sql)
        if stage1_sql != current_sql:
            repairs.extend(stage1_repairs)
            current_sql = stage1_sql

        # Stage 2: Schema / namespace prefix mapping and identifier normalization
        stage2_sql, stage2_repairs = self._repair_stage2_schema_identifiers(current_sql)
        if stage2_sql != current_sql:
            repairs.extend(stage2_repairs)
            current_sql = stage2_sql

        # Stage 3: Dialect built-in functions, types, and sequence syntax
        stage3_sql, stage3_repairs = self._repair_stage3_types_functions(current_sql)
        if stage3_sql != current_sql:
            repairs.extend(stage3_repairs)
            current_sql = stage3_sql

        return RepairResult(
            original_sql=sql,
            repaired_sql=current_sql,
            repairs_applied=repairs,
            is_modified=bool(repairs),
        )

    def _repair_stage1_directives(self, sql: str) -> tuple[str, list[str]]:
        repairs: list[str] = []
        cleaned = sql

        # Remove psql client slash commands (\c, \i, \set, etc.) at line start
        slash_match = re.search(r"^\s*\\[a-zA-Z]+.*$", cleaned, flags=re.MULTILINE)
        if slash_match:
            cleaned = re.sub(r"^\s*\\[a-zA-Z]+.*$", "", cleaned, flags=re.MULTILINE).strip()
            repairs.append("STRIPPED_CLIENT_SLASH_COMMAND")

        # Strip MySQL / Oracle DELIMITER declarations
        if re.search(r"\bDELIMITER\s+[/;]+", cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(r"\bDELIMITER\s+[/;]+", "", cleaned, flags=re.IGNORECASE).strip()
            repairs.append("STRIPPED_DELIMITER_DIRECTIVE")

        # Strip T-SQL GO delimiters
        if re.search(r"^\s*GO\s*$", cleaned, flags=re.MULTILINE | re.IGNORECASE):
            cleaned = re.sub(r"^\s*GO\s*$", "", cleaned, flags=re.MULTILINE | re.IGNORECASE).strip()
            repairs.append("STRIPPED_TSQL_GO_DIRECTIVE")

        return cleaned, repairs

    def _repair_stage2_schema_identifiers(self, sql: str) -> tuple[str, list[str]]:
        repairs: list[str] = []
        modified = sql

        # 1. Normalize bracket identifiers [col] -> "col"
        bracket_pattern = re.compile(r"\[([a-zA-Z0-9_]+)\]")
        if bracket_pattern.search(modified):
            modified = bracket_pattern.sub(r'"\1"', modified)
            repairs.append("NORMALIZED_BRACKET_IDENTIFIERS")

        # 2. Normalize backtick identifiers `col` -> "col"
        backtick_pattern = re.compile(r"`([a-zA-Z0-9_]+)`")
        if backtick_pattern.search(modified):
            modified = backtick_pattern.sub(r'"\1"', modified)
            repairs.append("NORMALIZED_BACKTICK_IDENTIFIERS")

        # 3. Apply namespace / schema mapping
        for src_schema, tgt_schema in self.namespace_map.items():
            if src_schema:
                schema_prefix_pattern = re.compile(
                    rf"\b{re.escape(src_schema)}\.([a-zA-Z0-9_\"]+)", flags=re.IGNORECASE
                )
                if schema_prefix_pattern.search(modified):
                    modified = schema_prefix_pattern.sub(rf"{tgt_schema}.\1", modified)
                    repairs.append(f"MAPPED_SCHEMA_{src_schema}_TO_{tgt_schema}")

        return modified, repairs

    def _repair_stage3_types_functions(self, sql: str) -> tuple[str, list[str]]:
        repairs: list[str] = []
        modified = sql

        # 1. Function translations: NVL, IFNULL, ISNULL -> COALESCE
        coalesce_pattern = re.compile(r"\b(?:NVL|IFNULL|ISNULL)\s*\(", flags=re.IGNORECASE)
        if coalesce_pattern.search(modified):
            modified = coalesce_pattern.sub("COALESCE(", modified)
            repairs.append("REWRITTEN_NULL_FUNCTION_TO_COALESCE")

        # 2. System date/time functions: SYSDATE / GETDATE() / NOW() -> CURRENT_TIMESTAMP
        sysdate_pattern = re.compile(r"\b(?:SYSDATE|GETDATE\(\))\b", flags=re.IGNORECASE)
        if sysdate_pattern.search(modified):
            modified = sysdate_pattern.sub("CURRENT_TIMESTAMP", modified)
            repairs.append("REWRITTEN_DATETIME_FUNCTION_TO_CURRENT_TIMESTAMP")

        # 3. Oracle / MySQL string length: LENGTH / CHAR_LENGTH normalization
        if self.target_dialect in {"postgresql", "dm8"}:
            len_pattern = re.compile(r"\bLEN\s*\(", flags=re.IGNORECASE)
            if len_pattern.search(modified):
                modified = len_pattern.sub("LENGTH(", modified)
                repairs.append("REWRITTEN_LEN_TO_LENGTH")

        # 4. Type translations:
        # VARCHAR2(n) -> VARCHAR(n)
        varchar2_pattern = re.compile(r"\bVARCHAR2\s*\((\d+)\)", flags=re.IGNORECASE)
        if varchar2_pattern.search(modified):
            modified = varchar2_pattern.sub(r"VARCHAR(\1)", modified)
            repairs.append("REWRITTEN_VARCHAR2_TO_VARCHAR")

        # NUMBER(p, s) -> DECIMAL(p, s), NUMBER -> NUMERIC
        number_ps_pattern = re.compile(r"\bNUMBER\s*\((\d+)\s*,\s*(\d+)\)", flags=re.IGNORECASE)
        if number_ps_pattern.search(modified):
            modified = number_ps_pattern.sub(r"DECIMAL(\1, \2)", modified)
            repairs.append("REWRITTEN_NUMBER_PS_TO_DECIMAL")

        number_p_pattern = re.compile(r"\bNUMBER\s*\((\d+)\)", flags=re.IGNORECASE)
        if number_p_pattern.search(modified):
            modified = number_p_pattern.sub(r"NUMERIC(\1)", modified)
            repairs.append("REWRITTEN_NUMBER_P_TO_NUMERIC")

        # CLOB -> TEXT
        clob_pattern = re.compile(r"\bCLOB\b", flags=re.IGNORECASE)
        if clob_pattern.search(modified):
            modified = clob_pattern.sub("TEXT", modified)
            repairs.append("REWRITTEN_CLOB_TO_TEXT")

        # BLOB -> BYTEA (if postgresql)
        if self.target_dialect == "postgresql":
            blob_pattern = re.compile(r"\bBLOB\b", flags=re.IGNORECASE)
            if blob_pattern.search(modified):
                modified = blob_pattern.sub("BYTEA", modified)
                repairs.append("REWRITTEN_BLOB_TO_BYTEA")

        # 5. Sequence auto-repair:
        if "SERIAL" in modified.upper() and self.target_dialect == "dm8":
            serial_pattern = re.compile(r"\bBIGSERIAL\b", flags=re.IGNORECASE)
            if serial_pattern.search(modified):
                modified = serial_pattern.sub("BIGINT IDENTITY(1, 1)", modified)
                repairs.append("REWRITTEN_BIGSERIAL_TO_IDENTITY")

            serial_pattern2 = re.compile(r"\bSERIAL\b", flags=re.IGNORECASE)
            if serial_pattern2.search(modified):
                modified = serial_pattern2.sub("INT IDENTITY(1, 1)", modified)
                repairs.append("REWRITTEN_SERIAL_TO_IDENTITY")

        return modified, repairs
