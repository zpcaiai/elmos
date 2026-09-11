"""Closed-Loop SQL Diagnostic & AST Self-Healing Engine.

Integrates real database execution diagnostics (e.g. SQLSTATE 42601 syntax errors,
unsupported types, identifier collisions) with AST and lexical transformation rules,
iterating through a closed-loop sandbox to repair and verify statements on the real database.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .sql_diagnostic_auto_repairer import SqlDiagnosticAutoRepairer

logger = logging.getLogger(__name__)


@dataclass
class HealingIteration:
    iteration: int
    attempted_sql: str
    error_sqlstate: str | None
    error_message: str
    repairs_applied: list[str]


@dataclass
class HealingReport:
    initial_sql: str
    final_sql: str
    success: bool
    iterations_count: int
    repairs_summary: list[str]
    history: list[HealingIteration] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "initialSql": self.initial_sql,
            "finalSql": self.final_sql,
            "success": self.success,
            "iterationsCount": self.iterations_count,
            "repairsSummary": self.repairs_summary,
            "error": self.error,
            "history": [
                {
                    "iteration": h.iteration,
                    "attemptedSql": h.attempted_sql,
                    "errorSqlstate": h.error_sqlstate,
                    "errorMessage": h.error_message,
                    "repairsApplied": h.repairs_applied,
                }
                for h in self.history
            ],
        }


class ClosedLoopSelfHealingEngine:
    """Executes SQL against real DB, catches execution errors, and iteratively heals them."""

    def __init__(
        self,
        connection: Any,
        target_dialect: str = "postgresql",
        max_iterations: int = 4,
    ) -> None:
        self.conn = connection
        self.target_dialect = target_dialect.lower()
        self.max_iterations = max_iterations
        self.base_repairer = SqlDiagnosticAutoRepairer(target_dialect=self.target_dialect)

    def execute_with_self_healing(self, sql: str, schema: str = "public") -> HealingReport:
        """Attempts execution with closed-loop self-healing on failure."""
        current_sql = sql.strip()
        history: list[HealingIteration] = []
        all_repairs: list[str] = []

        for it in range(1, self.max_iterations + 1):
            # Attempt execution inside a rollback-guarded subtransaction / savepoint
            success, sqlstate, err_msg = self._try_execute_statement(current_sql, schema=schema)
            if success:
                return HealingReport(
                    initial_sql=sql,
                    final_sql=current_sql,
                    success=True,
                    iterations_count=it,
                    repairs_summary=all_repairs,
                    history=history,
                )

            # Diagnose error and determine targeted repairs
            healed_sql, repairs = self._diagnose_and_heal(current_sql, sqlstate, err_msg)
            history.append(
                HealingIteration(
                    iteration=it,
                    attempted_sql=current_sql,
                    error_sqlstate=sqlstate,
                    error_message=err_msg,
                    repairs_applied=repairs,
                )
            )

            if not repairs or healed_sql == current_sql:
                # No more applicable healing strategies
                break

            all_repairs.extend(repairs)
            current_sql = healed_sql

        # Final verification attempt
        success, sqlstate, err_msg = self._try_execute_statement(current_sql, schema=schema)
        return HealingReport(
            initial_sql=sql,
            final_sql=current_sql,
            success=success,
            iterations_count=len(history) + 1,
            repairs_summary=all_repairs,
            history=history,
            error=None if success else f"[{sqlstate}] {err_msg}",
        )

    def _try_execute_statement(self, sql: str, schema: str) -> tuple[bool, str | None, str]:
        """Tries executing SQL using a savepoint to isolate failures."""
        was_autocommit = getattr(self.conn, "autocommit", False)
        self.conn.autocommit = False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SAVEPOINT elmos_heal_sp;")
                if schema and schema != "public":
                    cur.execute(f'SET search_path TO "{schema}", public;')
                cur.execute(sql)
                cur.execute("RELEASE SAVEPOINT elmos_heal_sp;")
            self.conn.commit()
            return True, None, ""
        except Exception as e:
            try:
                with self.conn.cursor() as cur:
                    cur.execute("ROLLBACK TO SAVEPOINT elmos_heal_sp;")
                    cur.execute("RELEASE SAVEPOINT elmos_heal_sp;")
                self.conn.commit()
            except Exception:
                self.conn.rollback()

            sqlstate = getattr(e, "pgcode", None)
            err_msg = str(e)
            return False, sqlstate, err_msg
        finally:
            self.conn.autocommit = was_autocommit

    def _diagnose_and_heal(
        self,
        sql: str,
        sqlstate: str | None,
        err_msg: str,
    ) -> tuple[str, list[str]]:
        """Diagnoses the failure mode and applies targeted syntactic AST corrections."""
        healed = sql
        repairs: list[str] = []

        # 1. Check for MySQL-style backticks
        if "`" in healed:
            healed = re.sub(r"`([^`]+)`", r'"\1"', healed)
            repairs.append("REPLACED_BACKTICKS_WITH_DOUBLE_QUOTES")

        # 2. Check for MSSQL-style brackets [col]
        if "[" in healed and "]" in healed:
            healed = re.sub(r"\[([a-zA-Z0-9_]+)\]", r'"\1"', healed)
            repairs.append("REPLACED_BRACKETS_WITH_DOUBLE_QUOTES")

        # 3. Check for Oracle VARCHAR2 / NUMBER / SYSDATE
        if "VARCHAR2" in healed.upper() or "NUMBER" in healed.upper() or "SYSDATE" in healed.upper() or "NVL" in healed.upper():
            base_res = self.base_repairer.repair_statement(healed)
            if base_res.is_modified:
                healed = base_res.repaired_sql
                repairs.extend(base_res.repairs_applied)

        # 4. Check for MySQL AUTO_INCREMENT -> SERIAL or IDENTITY
        if re.search(r"\bAUTO_INCREMENT\b", healed, flags=re.IGNORECASE):
            # If "INT AUTO_INCREMENT PRIMARY KEY" -> "SERIAL PRIMARY KEY"
            healed = re.sub(r"\b(?:BIGINT|INT|INTEGER)\s+AUTO_INCREMENT\b", "SERIAL", healed, flags=re.IGNORECASE)
            healed = re.sub(r"\bAUTO_INCREMENT\b", "", healed, flags=re.IGNORECASE)
            repairs.append("REWRITTEN_AUTO_INCREMENT_TO_SERIAL")

        # 5. Check for unquoted reserved keyword columns in PostgreSQL
        # e.g., syntax error at or near "order" or "user" or "group"
        reserved_match = re.search(r'syntax error at or near "([a-zA-Z0-9_]+)"', err_msg, flags=re.IGNORECASE)
        if reserved_match:
            bad_token = reserved_match.group(1)
            # Quote this token if it appears unquoted
            pattern = re.compile(rf'(?<!")\b({re.escape(bad_token)})\b(?!")', flags=re.IGNORECASE)
            healed = pattern.sub(rf'"{bad_token.lower()}"', healed)
            repairs.append(f"QUOTED_RESERVED_KEYWORD_{bad_token}")

        # 6. Check for MySQL LIMIT offset, count -> LIMIT count OFFSET offset
        mysql_limit = re.search(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)\b", healed, flags=re.IGNORECASE)
        if mysql_limit:
            offset = mysql_limit.group(1)
            count = mysql_limit.group(2)
            healed = re.sub(r"\bLIMIT\s+\d+\s*,\s*\d+\b", f"LIMIT {count} OFFSET {offset}", healed, flags=re.IGNORECASE)
            repairs.append("REWRITTEN_MYSQL_LIMIT_OFFSET")

        return healed, repairs
