"""Base class and common infrastructure for ChinaDB dedicated target lowerers.

Provides specialized lowering passes for DDL, procedural routines (PL/SQL, T-SQL, PL/pgSQL),
cursors, triggers, exception handling, data types, and dialect built-in functions.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DialectLoweringRule:
    """Transformation rule applied during AST lowering."""

    rule_id: str
    description: str
    pattern: str
    replacement: str
    is_regex: bool = False
    flags: int = 0
    applies_to_dialects: list[str] = field(default_factory=lambda: ["all"])


class ChinaDbTargetLowerer(ABC):
    """Abstract base lowerer for domestic database targets."""

    target_id: str
    display_name: str
    family: str  # "oracle_compat", "pg_compat", "mysql_compat", "informix_compat", "mpp"

    def __init__(self) -> None:
        self.type_mappings: dict[str, str] = self._build_type_mappings()
        self.builtin_mappings: dict[str, str] = self._build_builtin_mappings()
        self.lowering_rules: list[DialectLoweringRule] = self._build_lowering_rules()

    @abstractmethod
    def _build_type_mappings(self) -> dict[str, str]:
        """Build dictionary of source data types mapped to target dialect types."""

    @abstractmethod
    def _build_builtin_mappings(self) -> dict[str, str]:
        """Build dictionary of source built-in functions mapped to target equivalents."""

    @abstractmethod
    def _build_lowering_rules(self) -> list[DialectLoweringRule]:
        """Build dialect-specific transformation rules."""

    def lower_statement(
        self,
        source_sql: str,
        source_dialect: str,
        asset_kind: str = "STATEMENT",
    ) -> str:
        """Lower any SQL statement or procedural block to target dialect."""
        kind = asset_kind.upper()
        if "TABLE" in kind:
            return self.lower_table_ddl(source_sql, source_dialect)
        if "VIEW" in kind:
            return self.lower_view(source_sql, source_dialect)
        if "PROCEDURE" in kind:
            return self.lower_procedure(source_sql, source_dialect)
        if "FUNCTION" in kind:
            return self.lower_function(source_sql, source_dialect)
        if "TRIGGER" in kind:
            return self.lower_trigger(source_sql, source_dialect)
        if "SEQUENCE" in kind:
            return self.lower_sequence(source_sql, source_dialect)

        # Generic statement lowering
        sql = self.lower_data_types(source_sql, source_dialect)
        sql = self.lower_builtin_functions(sql, source_dialect)
        sql = self.apply_custom_rules(sql, source_dialect)
        return sql

    def lower_table_ddl(self, source_sql: str, source_dialect: str) -> str:
        """Lower CREATE TABLE and ALTER TABLE DDL."""
        sql = self.lower_data_types(source_sql, source_dialect)
        sql = self.lower_builtin_functions(sql, source_dialect)
        sql = self.apply_custom_rules(sql, source_dialect)
        return sql

    def lower_view(self, source_sql: str, source_dialect: str) -> str:
        """Lower CREATE VIEW DDL."""
        sql = self.lower_data_types(source_sql, source_dialect)
        sql = self.lower_builtin_functions(sql, source_dialect)
        sql = self.apply_custom_rules(sql, source_dialect)
        return sql

    @abstractmethod
    def lower_procedure(self, source_sql: str, source_dialect: str) -> str:
        """Lower stored procedure declaration and body to target dialect."""

    @abstractmethod
    def lower_function(self, source_sql: str, source_dialect: str) -> str:
        """Lower stored function declaration and body to target dialect."""

    @abstractmethod
    def lower_trigger(self, source_sql: str, source_dialect: str) -> str:
        """Lower trigger declaration, timing, and body to target dialect."""

    @abstractmethod
    def lower_sequence(self, source_sql: str, source_dialect: str) -> str:
        """Lower sequence creation and nextval references to target dialect."""

    def lower_data_types(self, sql: str, source_dialect: str) -> str:
        """Replace data types according to target dialect mapping table."""
        res = sql
        for src_type, tgt_type in self.type_mappings.items():
            pattern = rf"\b{re.escape(src_type)}\b"
            res = re.sub(pattern, tgt_type, res, flags=re.IGNORECASE)
        return res

    def lower_builtin_functions(self, sql: str, source_dialect: str) -> str:
        """Replace built-in functions with target equivalents."""
        res = sql
        for src_fn, tgt_fn in self.builtin_mappings.items():
            pattern = rf"\b{re.escape(src_fn)}\s*\("
            replacement = f"{tgt_fn}("
            res = re.sub(pattern, replacement, res, flags=re.IGNORECASE)
        return res

    def apply_custom_rules(self, sql: str, source_dialect: str) -> str:
        """Apply target-specific lowering rules sequentially."""
        res = sql
        src = source_dialect.lower()
        for rule in self.lowering_rules:
            if "all" in rule.applies_to_dialects or src in rule.applies_to_dialects:
                if rule.is_regex:
                    res = re.sub(rule.pattern, rule.replacement, res, flags=rule.flags)
                else:
                    res = res.replace(rule.pattern, rule.replacement)
        return res

    def verify_syntax_heuristics(self, sql: str) -> tuple[bool, list[str]]:
        """Heuristic static validation checking for untransformed legacy idioms."""
        issues: list[str] = []
        upper = sql.upper()
        # Common check: unmatched BEGIN/END
        begin_count = len(re.findall(r"\bBEGIN\b", upper))
        end_count = len(re.findall(r"\bEND\b", upper))
        if begin_count != end_count and begin_count > 0:
            issues.append(f"Block delimiter mismatch: {begin_count} BEGIN vs {end_count} END")

        return (len(issues) == 0, issues)
