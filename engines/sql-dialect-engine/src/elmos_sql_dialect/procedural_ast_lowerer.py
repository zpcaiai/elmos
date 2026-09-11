"""Industrial-grade Procedural SQL AST Lowerer for PL/SQL, T-SQL, and PL/pgSQL.

Translates complex stored procedures, functions, packages, triggers, control flow,
cursors, dynamic SQL, autonomous transactions, and exception handling across
PostgreSQL, Oracle, SQL Server (T-SQL), MySQL, and the 13 ChinaDB domestic targets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import Dialect, DialectError


class RoutineKind(str, Enum):
    PROCEDURE = "PROCEDURE"
    FUNCTION = "FUNCTION"
    TRIGGER = "TRIGGER"
    PACKAGE = "PACKAGE"


class ParamMode(str, Enum):
    IN = "IN"
    OUT = "OUT"
    INOUT = "INOUT"


@dataclass
class AstParam:
    name: str
    data_type: str
    mode: ParamMode = ParamMode.IN
    default_expr: str | None = None


@dataclass
class VariableDecl:
    name: str
    data_type: str
    default_expr: str | None = None
    is_constant: bool = False


@dataclass
class CursorDecl:
    name: str
    query_sql: str
    parameters: list[AstParam] = field(default_factory=list)


@dataclass
class AssignmentStmt:
    target: str
    expression: str


@dataclass
class SelectIntoStmt:
    select_expressions: list[str]
    into_variables: list[str]
    from_clause: str
    where_clause: str | None = None
    group_by: str | None = None
    having: str | None = None
    order_by: str | None = None
    limit: str | None = None


@dataclass
class IfBranch:
    condition: str
    statements: list[Any] = field(default_factory=list)


@dataclass
class IfStmt:
    branches: list[IfBranch] = field(default_factory=list)
    else_statements: list[Any] = field(default_factory=list)


@dataclass
class WhileStmt:
    condition: str
    statements: list[Any] = field(default_factory=list)


@dataclass
class ForRangeLoopStmt:
    loop_var: str
    lower_bound: str
    upper_bound: str
    reverse: bool = False
    statements: list[Any] = field(default_factory=list)


@dataclass
class CursorForLoopStmt:
    record_var: str
    cursor_or_query: str
    is_raw_query: bool = False
    statements: list[Any] = field(default_factory=list)


@dataclass
class SimpleLoopStmt:
    statements: list[Any] = field(default_factory=list)


@dataclass
class ExitWhenStmt:
    condition: str | None = None
    label: str | None = None


@dataclass
class ReturnStmt:
    expression: str | None = None


@dataclass
class CursorOpenStmt:
    cursor_name: str
    parameters: list[str] = field(default_factory=list)


@dataclass
class CursorFetchStmt:
    cursor_name: str
    into_variables: list[str] = field(default_factory=list)


@dataclass
class CursorCloseStmt:
    cursor_name: str


@dataclass
class RaiseStmt:
    exception_name: str | None = None
    error_code: int | None = None
    error_message: str | None = None


@dataclass
class ExecuteImmediateStmt:
    query_expr: str
    into_variables: list[str] = field(default_factory=list)
    using_parameters: list[str] = field(default_factory=list)


@dataclass
class TransactionStmt:
    action: str  # COMMIT, ROLLBACK, SAVEPOINT, ROLLBACK_TO
    savepoint_name: str | None = None


@dataclass
class AutonomousTxBlock:
    statements: list[Any] = field(default_factory=list)


@dataclass
class DmlStmt:
    sql: str
    kind: str  # INSERT, UPDATE, DELETE, MERGE


@dataclass
class RawStmt:
    text: str


@dataclass
class ExceptionHandler:
    exception_names: list[str]
    statements: list[Any] = field(default_factory=list)


@dataclass
class ExceptionSection:
    handlers: list[ExceptionHandler] = field(default_factory=list)
    others_handler: list[Any] | None = None


@dataclass
class ProcedureBlock:
    declarations: list[VariableDecl | CursorDecl] = field(default_factory=list)
    statements: list[Any] = field(default_factory=list)
    exception_section: ExceptionSection | None = None
    is_autonomous: bool = False


@dataclass
class RoutineDefinition:
    name: str
    kind: RoutineKind
    parameters: list[AstParam] = field(default_factory=list)
    return_type: str | None = None
    body: ProcedureBlock = field(default_factory=ProcedureBlock)
    schema: str | None = None
    or_replace: bool = False
    language: str = "SQL"
    comment: str | None = None


@dataclass
class TriggerDefinition:
    name: str
    table_name: str
    timing: str  # BEFORE, AFTER, INSTEAD OF
    events: list[str]  # INSERT, UPDATE, DELETE
    for_each_row: bool = True
    when_condition: str | None = None
    body: ProcedureBlock = field(default_factory=ProcedureBlock)
    schema: str | None = None
    or_replace: bool = False


@dataclass
class PackageSpec:
    name: str
    schema: str | None = None
    or_replace: bool = False
    variables: list[VariableDecl] = field(default_factory=list)
    routine_signatures: list[RoutineDefinition] = field(default_factory=list)
    custom_types: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PackageBody:
    name: str
    schema: str | None = None
    or_replace: bool = False
    private_variables: list[VariableDecl] = field(default_factory=list)
    routines: list[RoutineDefinition] = field(default_factory=list)
    initialization_statements: list[Any] = field(default_factory=list)


@dataclass
class PackageDefinition:
    name: str
    schema: str | None = None
    or_replace: bool = False
    spec: PackageSpec | None = None
    body: PackageBody | None = None


class ProceduralAstLowerer:
    """Master Procedural SQL AST Parser and Lowerer."""

    def __init__(self, target_dialect: Dialect | str = Dialect.POSTGRES) -> None:
        if isinstance(target_dialect, str):
            target_dialect = Dialect(target_dialect.lower())
        self.target_dialect = target_dialect

    # -------------------------------------------------------------------------
    # Parsing Entry Points
    # -------------------------------------------------------------------------
    def parse_routine(self, sql: str, source_dialect: Dialect = Dialect.ORACLE) -> RoutineDefinition:
        """Parse stored procedure or function into canonical RoutineDefinition AST."""
        clean_sql = self._clean_sql(sql)
        kind = RoutineKind.PROCEDURE if re.search(r"\bPROCEDURE\b", clean_sql, re.IGNORECASE) else RoutineKind.FUNCTION
        
        # Name and schema
        m_name = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)",
            clean_sql,
            re.IGNORECASE,
        )
        if not m_name:
            raise DialectError("ROUTINE_PARSE_FAILED", "Could not extract routine name")
        schema = m_name.group(1)
        name = m_name.group(2)
        or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m_name.end()], re.IGNORECASE))

        # Parameters
        params = self._parse_parameters(clean_sql, m_name.end())

        # Return type for functions
        return_type = None
        if kind == RoutineKind.FUNCTION:
            m_ret = re.search(r"\bRETURN\s+([A-Za-z0-9_]+(?:\s*\([^)]+\))?)", clean_sql, re.IGNORECASE)
            if m_ret:
                return_type = m_ret.group(1).strip()

        # Extract body block
        body = self._parse_body_block(clean_sql, source_dialect)

        return RoutineDefinition(
            name=name,
            kind=kind,
            parameters=params,
            return_type=return_type,
            body=body,
            schema=schema,
            or_replace=or_replace,
            language="PLSQL" if source_dialect in (Dialect.ORACLE, Dialect.TSQL) else "PLPGSQL",
        )

    def parse_trigger(self, sql: str, source_dialect: Dialect = Dialect.ORACLE) -> TriggerDefinition:
        """Parse database trigger into canonical TriggerDefinition AST."""
        clean_sql = self._clean_sql(sql)
        m_trig = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s+"
            r"(BEFORE|AFTER|INSTEAD\s+OF)\s+([A-Za-z0-9_,\s]+)\s+ON\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)",
            clean_sql,
            re.IGNORECASE,
        )
        if not m_trig:
            raise DialectError("TRIGGER_PARSE_FAILED", "Could not extract trigger metadata")
        
        schema = m_trig.group(1)
        name = m_trig.group(2)
        timing = m_trig.group(3).upper()
        raw_events = m_trig.group(4).upper()
        events = [e.strip() for e in re.split(r"\s+OR\s+|\s*,\s*", raw_events) if e.strip()]
        table_name = m_trig.group(6)
        or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m_trig.end()], re.IGNORECASE))
        for_each_row = bool(re.search(r"FOR\s+EACH\s+ROW", clean_sql, re.IGNORECASE))

        # WHEN condition
        when_condition = None
        m_when = re.search(r"WHEN\s*\((.*?)\)", clean_sql, re.IGNORECASE)
        if m_when:
            when_condition = m_when.group(1).strip()

        body = self._parse_body_block(clean_sql, source_dialect)

        return TriggerDefinition(
            name=name,
            table_name=table_name,
            timing=timing,
            events=events,
            for_each_row=for_each_row,
            when_condition=when_condition,
            body=body,
            schema=schema,
            or_replace=or_replace,
        )

    def parse_package(
        self,
        sql: str = "",
        source_dialect: Dialect = Dialect.ORACLE,
        spec_sql: str | None = None,
        body_sql: str | None = None,
    ) -> PackageDefinition:
        """Parse Oracle/DM8 package specification and body into PackageDefinition AST."""
        spec: PackageSpec | None = None
        body: PackageBody | None = None

        if spec_sql is not None and body_sql is not None:
            spec = self.parse_package_spec(spec_sql, source_dialect)
            body = self.parse_package_body(body_sql, source_dialect)
            return PackageDefinition(
                name=spec.name or body.name,
                schema=spec.schema or body.schema,
                or_replace=spec.or_replace or body.or_replace,
                spec=spec,
                body=body,
            )

        clean_sql = self._clean_sql(sql)
        m_body = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+BODY\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)",
            clean_sql,
            re.IGNORECASE,
        )
        m_spec = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+(?!BODY\b)(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)",
            clean_sql,
            re.IGNORECASE,
        )

        pkg_name = "unknown_package"
        pkg_schema = None
        or_replace = False

        if m_spec and m_body:
            pkg_schema = m_spec.group(1) or m_body.group(1)
            pkg_name = m_spec.group(2) or m_body.group(2)
            or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m_spec.end()], re.IGNORECASE))
            if m_body.start() > m_spec.start():
                spec_sql = clean_sql[m_spec.start() : m_body.start()]
                body_sql = clean_sql[m_body.start() :]
            else:
                body_sql = clean_sql[m_body.start() : m_spec.start()]
                spec_sql = clean_sql[m_spec.start() :]
            spec = self.parse_package_spec(spec_sql, source_dialect)
            body = self.parse_package_body(body_sql, source_dialect)
        elif m_spec:
            pkg_schema = m_spec.group(1)
            pkg_name = m_spec.group(2)
            or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m_spec.end()], re.IGNORECASE))
            spec = self.parse_package_spec(clean_sql, source_dialect)
        elif m_body:
            pkg_schema = m_body.group(1)
            pkg_name = m_body.group(2)
            or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m_body.end()], re.IGNORECASE))
            body = self.parse_package_body(clean_sql, source_dialect)
        else:
            raise DialectError("PACKAGE_PARSE_FAILED", "Could not extract package metadata")

        return PackageDefinition(
            name=pkg_name,
            schema=pkg_schema,
            or_replace=or_replace,
            spec=spec,
            body=body,
        )

    def parse_package_spec(self, sql: str, source_dialect: Dialect = Dialect.ORACLE) -> PackageSpec:
        """Parse package specification (public signatures and variables)."""
        clean_sql = self._clean_sql(sql)
        m = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s+(?:IS|AS)\b(.*)\bEND(?:\s+[A-Za-z0-9_]+)?\s*;?",
            clean_sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            raise DialectError("PACKAGE_SPEC_PARSE_FAILED", "Invalid package specification syntax")

        schema = m.group(1)
        name = m.group(2)
        or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m.start(3)], re.IGNORECASE))
        inner_content = m.group(3).strip()

        variables: list[VariableDecl] = []
        routine_signatures: list[RoutineDefinition] = []

        stmts = [s.strip() for s in inner_content.split(";") if s.strip()]
        for stmt in stmts:
            upper = stmt.upper()
            if upper.startswith("PROCEDURE ") or upper.startswith("FUNCTION "):
                kind = RoutineKind.PROCEDURE if upper.startswith("PROCEDURE ") else RoutineKind.FUNCTION
                m_sig = re.search(r"^(?:PROCEDURE|FUNCTION)\s+([A-Za-z0-9_]+)", stmt, re.IGNORECASE)
                if m_sig:
                    r_name = m_sig.group(1)
                    params = self._parse_parameters(stmt, m_sig.end())
                    ret_type = None
                    if kind == RoutineKind.FUNCTION:
                        m_ret = re.search(r"\bRETURN\s+([A-Za-z0-9_]+(?:\s*\([^)]+\))?)", stmt, re.IGNORECASE)
                        if m_ret:
                            ret_type = m_ret.group(1).strip()
                    routine_signatures.append(
                        RoutineDefinition(
                            name=r_name,
                            kind=kind,
                            parameters=params,
                            return_type=ret_type,
                            schema=name,
                        )
                    )
            else:
                decl = self._parse_variable_decl(stmt)
                if decl:
                    variables.append(decl)

        return PackageSpec(
            name=name,
            schema=schema,
            or_replace=or_replace,
            variables=variables,
            routine_signatures=routine_signatures,
        )

    def parse_package_body(self, sql: str, source_dialect: Dialect = Dialect.ORACLE) -> PackageBody:
        """Parse package body (private variables, routine implementations, init block)."""
        clean_sql = self._clean_sql(sql)
        m = re.search(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+BODY\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s+(?:IS|AS)\b(.*)",
            clean_sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            raise DialectError("PACKAGE_BODY_PARSE_FAILED", "Invalid package body syntax")

        schema = m.group(1)
        name = m.group(2)
        or_replace = bool(re.search(r"OR\s+REPLACE", clean_sql[: m.start(3)], re.IGNORECASE))
        body_content = m.group(3).strip()
        body_content = re.sub(r"\bEND(?:\s+[A-Za-z0-9_]+)?\s*;?$", "", body_content, flags=re.IGNORECASE).strip()

        private_vars: list[VariableDecl] = []
        routines: list[RoutineDefinition] = []
        init_stmts: list[Any] = []

        routine_pattern = re.compile(
            r"\b(PROCEDURE|FUNCTION)\s+([A-Za-z0-9_]+)\b.*?\bEND(?:\s+[A-Za-z0-9_]+)?\s*;",
            re.IGNORECASE | re.DOTALL,
        )

        last_end = 0
        for match in routine_pattern.finditer(body_content):
            preceding = body_content[last_end : match.start()].strip()
            if preceding:
                for line in preceding.split(";"):
                    line = line.strip()
                    if line:
                        decl = self._parse_variable_decl(line)
                        if decl:
                            private_vars.append(decl)

            routine_text = match.group(0)
            pseudo_sql = f"CREATE OR REPLACE {routine_text}"
            parsed_r = self.parse_routine(pseudo_sql, source_dialect)
            parsed_r.schema = name
            routines.append(parsed_r)
            last_end = match.end()

        trailing = body_content[last_end:].strip()
        if trailing:
            m_init = re.search(r"^\s*BEGIN\b\s*(.*)", trailing, re.IGNORECASE | re.DOTALL)
            if m_init:
                init_stmts = self._parse_statement_list(m_init.group(1))
            else:
                for line in trailing.split(";"):
                    line = line.strip()
                    if line:
                        decl = self._parse_variable_decl(line)
                        if decl:
                            private_vars.append(decl)

        return PackageBody(
            name=name,
            schema=schema,
            or_replace=or_replace,
            private_variables=private_vars,
            routines=routines,
            initialization_statements=init_stmts,
        )

    # -------------------------------------------------------------------------
    # Parsing Helpers
    # -------------------------------------------------------------------------
    def _clean_sql(self, sql: str) -> str:
        # Strip comments
        sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        return sql.strip()

    def _parse_parameters(self, sql: str, start_pos: int) -> list[AstParam]:
        sub = sql[start_pos:]
        m_head = re.search(r"\b(AS|IS|BEGIN)\b", sub, re.IGNORECASE)
        head_text = sub[: m_head.start()] if m_head else sub
        m_paren = re.search(r"\((.*?)\)", head_text, re.DOTALL)
        if not m_paren:
            # T-SQL can declare parameters without parens
            if "@" in head_text:
                return self._parse_param_list(head_text, is_tsql=True)
            return []
        return self._parse_param_list(m_paren.group(1), is_tsql=False)


    def _parse_param_list(self, text: str, is_tsql: bool = False) -> list[AstParam]:
        params: list[AstParam] = []
        raw_items = [p.strip() for p in text.split(",") if p.strip()]
        for item in raw_items:
            # Check default
            default_val = None
            if ":=" in item:
                item, default_val = item.split(":=", 1)
            elif "DEFAULT" in item.upper():
                parts = re.split(r"\bDEFAULT\b", item, flags=re.IGNORECASE)
                item, default_val = parts[0], parts[1]
            elif "=" in item:
                item, default_val = item.split("=", 1)

            tokens = item.strip().split()
            if not tokens:
                continue

            if is_tsql or tokens[0].startswith("@"):
                p_name = tokens[0]
                p_type = tokens[1] if len(tokens) > 1 else "VARCHAR"
                mode = ParamMode.OUT if any(t.upper() in ("OUT", "OUTPUT") for t in tokens) else ParamMode.IN
            else:
                p_name = tokens[0]
                mode = ParamMode.IN
                type_start = 1
                if len(tokens) > 1 and tokens[1].upper() in ("IN", "OUT", "INOUT"):
                    mode = ParamMode(tokens[1].upper())
                    type_start = 2
                p_type = " ".join(tokens[type_start:]) if type_start < len(tokens) else "VARCHAR"

            params.append(
                AstParam(
                    name=p_name.strip(),
                    data_type=p_type.strip(),
                    mode=mode,
                    default_expr=default_val.strip() if default_val else None,
                )
            )
        return params

    def _parse_body_block(self, sql: str, source_dialect: Dialect) -> ProcedureBlock:
        is_autonomous = bool(re.search(r"PRAGMA\s+AUTONOMOUS_TRANSACTION", sql, re.IGNORECASE))
        decls: list[VariableDecl | CursorDecl] = []

        # Find declarations section (between IS/AS/DECLARE and BEGIN)
        m_begin = re.search(r"\bBEGIN\b", sql, re.IGNORECASE)
        if m_begin:
            pre_begin = sql[: m_begin.start()]
            m_decl_start = re.search(r"\b(DECLARE|AS|IS)\b", pre_begin, re.IGNORECASE)
            if m_decl_start:
                decl_text = pre_begin[m_decl_start.end() :]
                decls = self._parse_declarations(decl_text)
            body_text = sql[m_begin.end() :]
        else:
            body_text = sql

        statements: list[Any] = []
        exception_section: ExceptionSection | None = None

        m_exc = re.search(r"\bEXCEPTION\b", body_text, re.IGNORECASE)
        m_try_catch = re.search(r"\bBEGIN\s+CATCH\b", body_text, re.IGNORECASE)

        if m_exc:
            stmt_text = body_text[: m_exc.start()]
            exc_text = body_text[m_exc.end() :]
            exception_section = self._parse_exception_section(exc_text)
        elif m_try_catch:
            stmt_text = body_text[: m_try_catch.start()]
            catch_text = body_text[m_try_catch.end() :]
            exception_section = self._parse_catch_section(catch_text)
        else:
            stmt_text = body_text

        # Strip trailing END [name];
        stmt_text = re.sub(r"\bEND(?:\s+[A-Za-z0-9_]+)?\s*;?\s*$", "", stmt_text.strip(), flags=re.IGNORECASE)

        statements = self._parse_statement_list(stmt_text)

        return ProcedureBlock(
            declarations=decls,
            statements=statements,
            exception_section=exception_section,
            is_autonomous=is_autonomous,
        )

    def _parse_declarations(self, decl_text: str) -> list[VariableDecl | CursorDecl]:
        results: list[VariableDecl | CursorDecl] = []
        lines = [s.strip() for s in decl_text.split(";") if s.strip()]
        for line in lines:
            if re.search(r"PRAGMA\s+AUTONOMOUS_TRANSACTION", line, re.IGNORECASE):
                continue
            m_cur = re.search(r"CURSOR\s+([A-Za-z0-9_]+)\s+IS\s+(.*)", line, re.IGNORECASE | re.DOTALL)
            if m_cur:
                c_name = m_cur.group(1).strip()
                c_query = m_cur.group(2).strip()
                results.append(CursorDecl(name=c_name, query_sql=c_query))
                continue

            decl = self._parse_variable_decl(line)
            if decl:
                results.append(decl)
        return results

    def _parse_variable_decl(self, line: str) -> VariableDecl | None:
        clean_line = re.sub(r"^\s*DECLARE\s+", "", line, flags=re.IGNORECASE).strip()
        if not clean_line or clean_line.startswith("--"):
            return None
        is_constant = bool(re.search(r"\bCONSTANT\b", clean_line, re.IGNORECASE))
        clean_line = re.sub(r"\bCONSTANT\b", "", clean_line, flags=re.IGNORECASE).strip()

        default_val = None
        if ":=" in clean_line:
            clean_line, default_val = clean_line.split(":=", 1)
        elif "DEFAULT" in clean_line.upper():
            parts = re.split(r"\bDEFAULT\b", clean_line, flags=re.IGNORECASE)
            clean_line, default_val = parts[0], parts[1]
        elif "=" in clean_line:
            clean_line, default_val = clean_line.split("=", 1)

        tokens = clean_line.strip().split()
        if len(tokens) >= 2:
            v_name = tokens[0]
            v_type = " ".join(tokens[1:])
            return VariableDecl(
                name=v_name,
                data_type=v_type,
                default_expr=default_val.strip() if default_val else None,
                is_constant=is_constant,
            )
        return None

    def _parse_statement_list(self, text: str) -> list[Any]:
        statements: list[Any] = []
        raw_stmts = self._split_procedural_statements(text)
        for s in raw_stmts:
            parsed = self._parse_single_statement(s)
            if parsed:
                statements.append(parsed)
        return statements

    def _split_procedural_statements(self, text: str) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        depth = 0
        pattern = re.compile(
            r"(\bBEGIN\b|\bCASE\b|\bLOOP\b|\bIF\b|\bEND\s+IF\b|\bEND\s+LOOP\b|\bEND\s+CASE\b|\bEND\b|;)",
            re.IGNORECASE,
        )
        pos = 0
        for m in pattern.finditer(text):
            tok = m.group(1)
            current.append(text[pos:m.end()])
            pos = m.end()
            tok_upper = re.sub(r"\s+", " ", tok.strip().upper())

            if tok_upper in ("BEGIN", "CASE", "LOOP", "IF"):
                depth += 1
            elif tok_upper in ("END IF", "END LOOP", "END CASE", "END"):
                depth = max(0, depth - 1)
            elif tok == ";" and depth == 0:
                stmt = "".join(current).strip()
                if stmt and stmt != ";":
                    chunks.append(stmt)
                current = []

        if pos < len(text):
            current.append(text[pos:])
        remainder = "".join(current).strip()
        if remainder and remainder != ";":
            chunks.append(remainder)
        return chunks


    def _parse_single_statement(self, stmt: str) -> Any:
        stmt = stmt.strip()
        if not stmt or stmt == ";":
            return None

        inner = stmt.rstrip(";").strip()
        upper = inner.upper()

        if upper.startswith("IF ") or upper.startswith("IF("):
            return self._parse_if_statement(inner)

        if upper.startswith("WHILE "):
            return self._parse_while_statement(inner)

        if upper.startswith("FOR ") and " LOOP" in upper:
            return self._parse_for_statement(inner)

        if upper.startswith("LOOP") and upper.endswith("END LOOP"):
            body_text = inner[4:-8].strip()
            return SimpleLoopStmt(statements=self._parse_statement_list(body_text))

        if upper.startswith("EXIT"):
            m_exit = re.search(r"EXIT(?:\s+([A-Za-z0-9_]+))?(?:\s+WHEN\s+(.*))?", inner, re.IGNORECASE)
            if m_exit:
                return ExitWhenStmt(label=m_exit.group(1), condition=m_exit.group(2))
            return ExitWhenStmt()

        if upper.startswith("RETURN"):
            ret_expr = inner[6:].strip()
            return ReturnStmt(expression=ret_expr if ret_expr else None)

        if upper.startswith("EXECUTE IMMEDIATE "):
            return self._parse_execute_immediate(inner)
        if upper.startswith("EXEC SP_EXECUTESQL") or upper.startswith("EXECUTE SP_EXECUTESQL"):
            return self._parse_tsql_executesql(inner)

        if upper.startswith("OPEN "):
            c_name = inner[5:].strip()
            return CursorOpenStmt(cursor_name=c_name)
        if upper.startswith("FETCH "):
            m_fetch = re.search(r"FETCH(?:\s+NEXT\s+FROM)?\s+([A-Za-z0-9_]+)\s+INTO\s+(.*)", inner, re.IGNORECASE)
            if m_fetch:
                c_name = m_fetch.group(1).strip()
                into_vars = [v.strip() for v in m_fetch.group(2).split(",")]
                return CursorFetchStmt(cursor_name=c_name, into_variables=into_vars)
        if upper.startswith("CLOSE "):
            c_name = inner[6:].strip()
            return CursorCloseStmt(cursor_name=c_name)

        if upper.startswith("RAISE ") or upper.startswith("THROW "):
            return self._parse_raise_statement(inner)

        if upper in ("COMMIT", "COMMIT WORK", "COMMIT TRANSACTION", "COMMIT TRAN"):
            return TransactionStmt(action="COMMIT")
        if upper in ("ROLLBACK", "ROLLBACK WORK", "ROLLBACK TRANSACTION", "ROLLBACK TRAN"):
            return TransactionStmt(action="ROLLBACK")
        if upper.startswith("SAVEPOINT ") or upper.startswith("SAVE TRANSACTION ") or upper.startswith("SAVE TRAN "):
            sp_name = inner.split()[-1]
            return TransactionStmt(action="SAVEPOINT", savepoint_name=sp_name)
        if "ROLLBACK TO" in upper or "ROLLBACK TRANSACTION " in upper or "ROLLBACK TRAN " in upper:
            sp_name = inner.split()[-1]
            return TransactionStmt(action="ROLLBACK_TO", savepoint_name=sp_name)

        if upper.startswith("SELECT ") and " INTO " in upper:
            return self._parse_select_into(inner)

        if ":=" in inner:
            lhs, rhs = inner.split(":=", 1)
            return AssignmentStmt(target=lhs.strip(), expression=rhs.strip())
        if upper.startswith("SET "):
            assign_part = inner[4:].strip()
            if "=" in assign_part:
                lhs, rhs = assign_part.split("=", 1)
                return AssignmentStmt(target=lhs.strip(), expression=rhs.strip())

        for dml_kw in ("INSERT INTO", "INSERT", "UPDATE", "DELETE FROM", "DELETE", "MERGE INTO", "MERGE"):
            if upper.startswith(dml_kw + " ") or upper.startswith(dml_kw + "\n"):
                return DmlStmt(sql=inner + ";", kind=dml_kw.split()[0])

        return RawStmt(text=inner + ";")

    def _parse_if_statement(self, text: str) -> IfStmt:
        branches: list[IfBranch] = []
        else_stmts: list[Any] = []

        clean = re.sub(r"\bEND(?:\s+IF)?\s*;?$", "", text.strip(), flags=re.IGNORECASE).strip()
        parts = re.split(r"\b(ELSIF|ELSE\s+IF|ELSE)\b", clean, flags=re.IGNORECASE)
        first = parts[0]
        m_if = re.search(r"^\s*IF\s+(.*?)\s+(?:THEN|BEGIN)\s+(.*)", first, re.IGNORECASE | re.DOTALL)
        if m_if:
            branches.append(
                IfBranch(
                    condition=m_if.group(1).strip(),
                    statements=self._parse_statement_list(m_if.group(2)),
                )
            )

        i = 1
        while i < len(parts):
            kw = parts[i].upper().replace(" ", "")
            content = parts[i + 1] if i + 1 < len(parts) else ""
            if kw in ("ELSIF", "ELSEIF"):
                m_elsif = re.search(r"^\s*(.*?)\s+(?:THEN|BEGIN)\s+(.*)", content, re.IGNORECASE | re.DOTALL)
                if m_elsif:
                    branches.append(
                        IfBranch(
                            condition=m_elsif.group(1).strip(),
                            statements=self._parse_statement_list(m_elsif.group(2)),
                        )
                    )
            elif kw == "ELSE":
                m_else_begin = re.search(r"^\s*(?:BEGIN\s+)?(.*)", content, re.IGNORECASE | re.DOTALL)
                else_text = m_else_begin.group(1) if m_else_begin else content
                else_stmts = self._parse_statement_list(else_text)
            i += 2

        return IfStmt(branches=branches, else_statements=else_stmts)

    def _parse_while_statement(self, text: str) -> WhileStmt:
        clean = re.sub(r"\bEND(?:\s+LOOP)?\s*;?$", "", text.strip(), flags=re.IGNORECASE).strip()
        m_while = re.search(r"^\s*WHILE\s+(.*?)\s+(?:LOOP|BEGIN)\s+(.*)", clean, re.IGNORECASE | re.DOTALL)
        if m_while:
            return WhileStmt(
                condition=m_while.group(1).strip(),
                statements=self._parse_statement_list(m_while.group(2)),
            )
        return WhileStmt(condition="1=1", statements=[])

    def _parse_for_statement(self, text: str) -> Any:
        clean = re.sub(r"\bEND\s+LOOP\s*;?$", "", text.strip(), flags=re.IGNORECASE).strip()
        m_range = re.search(
            r"^\s*FOR\s+([A-Za-z0-9_]+)\s+IN\s+(REVERSE\s+)?([A-Za-z0-9_()+\-*/\s]+)\.\.([A-Za-z0-9_()+\-*/\s]+)\s+LOOP\s+(.*)",
            clean,
            re.IGNORECASE | re.DOTALL,
        )
        if m_range:
            loop_var = m_range.group(1).strip()
            reverse = bool(m_range.group(2))
            low = m_range.group(3).strip()
            high = m_range.group(4).strip()
            body = m_range.group(5)
            return ForRangeLoopStmt(
                loop_var=loop_var,
                lower_bound=low,
                upper_bound=high,
                reverse=reverse,
                statements=self._parse_statement_list(body),
            )

        m_cur = re.search(
            r"^\s*FOR\s+([A-Za-z0-9_]+)\s+IN\s+(?:\((.*?)\)|([A-Za-z0-9_]+))\s+LOOP\s+(.*)",
            clean,
            re.IGNORECASE | re.DOTALL,
        )
        if m_cur:
            rec_var = m_cur.group(1).strip()
            raw_query = m_cur.group(2)
            cur_name = m_cur.group(3)
            body = m_cur.group(4)
            return CursorForLoopStmt(
                record_var=rec_var,
                cursor_or_query=(raw_query or cur_name).strip(),
                is_raw_query=bool(raw_query),
                statements=self._parse_statement_list(body),
            )
        return RawStmt(text=text + ";")

    def _parse_select_into(self, text: str) -> SelectIntoStmt:
        m_sel = re.search(r"SELECT\s+(.*?)\s+INTO\s+(.*?)\s+FROM\s+(.*)", text, re.IGNORECASE | re.DOTALL)
        if not m_sel:
            return SelectIntoStmt(select_expressions=["*"], into_variables=["v"], from_clause="dual")

        select_part = m_sel.group(1).strip()
        into_part = m_sel.group(2).strip()
        rest = m_sel.group(3).strip()

        select_exprs = [e.strip() for e in select_part.split(",")]
        into_vars = [v.strip() for v in into_part.split(",")]

        where_clause = None
        from_clause = rest
        m_where = re.search(r"\bWHERE\b\s+(.*)", rest, re.IGNORECASE | re.DOTALL)
        if m_where:
            from_clause = rest[: m_where.start()].strip()
            where_clause = m_where.group(1).strip()

        return SelectIntoStmt(
            select_expressions=select_exprs,
            into_variables=into_vars,
            from_clause=from_clause,
            where_clause=where_clause,
        )

    def _parse_execute_immediate(self, text: str) -> ExecuteImmediateStmt:
        sub = text[18:].strip()
        into_vars: list[str] = []
        using_params: list[str] = []

        m_into = re.search(r"\bINTO\b\s+(.*?)(?=\bUSING\b|$)", sub, re.IGNORECASE | re.DOTALL)
        if m_into:
            into_vars = [v.strip() for v in m_into.group(1).split(",")]

        m_using = re.search(r"\bUSING\b\s+(.*)", sub, re.IGNORECASE | re.DOTALL)
        if m_using:
            using_params = [p.strip() for p in m_using.group(1).split(",")]

        query_end = len(sub)
        if m_into:
            query_end = min(query_end, m_into.start())
        if m_using:
            query_end = min(query_end, m_using.start())

        query_expr = sub[:query_end].strip()
        return ExecuteImmediateStmt(
            query_expr=query_expr,
            into_variables=into_vars,
            using_parameters=using_params,
        )

    def _parse_tsql_executesql(self, text: str) -> ExecuteImmediateStmt:
        sub = re.sub(r"^\s*EXEC(?:UTE)?\s+SP_EXECUTESQL\s+", "", text, flags=re.IGNORECASE).strip()
        args = [a.strip() for a in sub.split(",")]
        query_expr = args[0] if args else "''"
        using_params = args[2:] if len(args) > 2 else []
        return ExecuteImmediateStmt(query_expr=query_expr, using_parameters=using_params)

    def _parse_raise_statement(self, text: str) -> RaiseStmt:
        m_app_err = re.search(r"RAISE_APPLICATION_ERROR\s*\(\s*(-?\d+)\s*,\s*(.*?)\s*\)", text, re.IGNORECASE)
        if m_app_err:
            return RaiseStmt(
                error_code=int(m_app_err.group(1)),
                error_message=m_app_err.group(2).strip(),
            )
        m_throw = re.search(r"THROW\s+(\d+)\s*,\s*(.*?)\s*,\s*\d+", text, re.IGNORECASE)
        if m_throw:
            return RaiseStmt(
                error_code=int(m_throw.group(1)),
                error_message=m_throw.group(2).strip(),
            )
        tokens = text.split()
        if len(tokens) >= 2:
            return RaiseStmt(exception_name=tokens[1].rstrip(";"))
        return RaiseStmt()

    def _parse_exception_section(self, text: str) -> ExceptionSection:
        handlers: list[ExceptionHandler] = []
        others_handler: list[Any] | None = None

        clean = re.sub(r"\bEND(?:\s+[A-Za-z0-9_]+)?\s*;?$", "", text.strip(), flags=re.IGNORECASE).strip()
        parts = re.split(r"\bWHEN\b", clean, flags=re.IGNORECASE)

        for p in parts:
            if not p.strip():
                continue
            m_then = re.search(r"^(.*?)\bTHEN\b\s*(.*)", p, re.IGNORECASE | re.DOTALL)
            if m_then:
                exc_names = [e.strip() for e in re.split(r"\s+OR\s+", m_then.group(1).strip(), flags=re.IGNORECASE)]
                stmts = self._parse_statement_list(m_then.group(2))
                if any(e.upper() == "OTHERS" for e in exc_names):
                    others_handler = stmts
                else:
                    handlers.append(ExceptionHandler(exception_names=exc_names, statements=stmts))

        return ExceptionSection(handlers=handlers, others_handler=others_handler)

    def _parse_catch_section(self, text: str) -> ExceptionSection:
        clean = re.sub(r"\bEND\s+CATCH\s*;?$", "", text.strip(), flags=re.IGNORECASE).strip()
        stmts = self._parse_statement_list(clean)
        return ExceptionSection(others_handler=stmts)

    # -------------------------------------------------------------------------
    # Target Lowering / Emission
    # -------------------------------------------------------------------------
    def lower_routine(self, routine: RoutineDefinition, target_dialect: Dialect | str | None = None) -> str:
        """Lower RoutineDefinition AST into target SQL dialect string."""
        td = Dialect(target_dialect.lower()) if target_dialect else self.target_dialect
        if td == Dialect.POSTGRES:
            return self._emit_postgres_routine(routine)
        elif td == Dialect.ORACLE:
            return self._emit_oracle_routine(routine)
        elif td == Dialect.TSQL:
            return self._emit_tsql_routine(routine)
        elif td == Dialect.MYSQL:
            return self._emit_mysql_routine(routine)
        raise DialectError("UNSUPPORTED_TARGET", f"Dialect {td} is not supported")

    def parse_body_block(self, sql: str, source_dialect: Dialect = Dialect.ORACLE) -> ProcedureBlock:
        clean_sql = self._clean_sql(sql)
        return self._parse_body_block(clean_sql, source_dialect)

    def lower_block(self, block: ProcedureBlock, target_dialect: Dialect | str | None = None) -> str:
        dummy_routine = RoutineDefinition(
            name="anon_block",
            kind=RoutineKind.PROCEDURE,
            parameters=[],
            body=block,
        )
        return self.lower_routine(dummy_routine, target_dialect=target_dialect)

    def lower_trigger(self, trigger: TriggerDefinition, target_dialect: Dialect | str | None = None) -> str:
        """Lower TriggerDefinition AST into target SQL dialect string."""
        td = Dialect(target_dialect.lower()) if target_dialect else self.target_dialect
        if td == Dialect.POSTGRES:
            return self._emit_postgres_trigger(trigger)
        elif td == Dialect.ORACLE:
            return self._emit_oracle_trigger(trigger)
        elif td == Dialect.TSQL:
            return self._emit_tsql_trigger(trigger)
        elif td == Dialect.MYSQL:
            return self._emit_mysql_trigger(trigger)
        raise DialectError("UNSUPPORTED_TARGET", f"Dialect {td} is not supported")

    def lower_package(self, package: PackageDefinition, target_dialect: Dialect | str | None = None) -> str:
        """Lower PackageDefinition AST into target SQL dialect string."""
        td = Dialect(target_dialect.lower()) if target_dialect else self.target_dialect
        if td == Dialect.POSTGRES:
            return self._emit_postgres_package(package)
        elif td == Dialect.ORACLE:
            return self._emit_oracle_package(package)
        elif td == Dialect.TSQL:
            return self._emit_tsql_package(package)
        elif td == Dialect.MYSQL:
            return self._emit_mysql_package(package)
        raise DialectError("UNSUPPORTED_TARGET", f"Dialect {td} is not supported")



    # -------------------------------------------------------------------------
    # PostgreSQL Emitters
    # -------------------------------------------------------------------------
    def _emit_postgres_routine(self, r: RoutineDefinition) -> str:
        lines: list[str] = []
        kind_str = "PROCEDURE" if r.kind == RoutineKind.PROCEDURE else "FUNCTION"
        replace_str = "OR REPLACE " if r.or_replace else ""
        obj_name = f"{r.schema}.{r.name}" if r.schema else r.name

        param_strs: list[str] = []
        for p in r.parameters:
            mode_str = f"{p.mode.value} " if p.mode != ParamMode.IN else ""
            default_str = f" DEFAULT {p.default_expr}" if p.default_expr else ""
            param_strs.append(f"{p.name} {mode_str}{self._map_type(p.data_type, Dialect.POSTGRES)}{default_str}")

        lines.append(f"CREATE {replace_str}{kind_str} {obj_name}({', '.join(param_strs)})")
        if r.kind == RoutineKind.FUNCTION and r.return_type:
            lines.append(f"RETURNS {self._map_type(r.return_type, Dialect.POSTGRES)}")

        lines.append("LANGUAGE plpgsql")
        lines.append("AS $$")

        if r.body.is_autonomous:
            lines.append("    -- [Autonomous Transaction]: Lowered to independent procedure execution context")

        if r.body.declarations:
            lines.append("DECLARE")
            for d in r.body.declarations:
                if isinstance(d, VariableDecl):
                    c_str = "CONSTANT " if d.is_constant else ""
                    def_str = f" := {self._normalize_expr(d.default_expr, Dialect.POSTGRES)}" if d.default_expr else ""
                    lines.append(f"    {d.name} {c_str}{self._map_type(d.data_type, Dialect.POSTGRES)}{def_str};")
                elif isinstance(d, CursorDecl):
                    lines.append(f"    {d.name} CURSOR FOR {d.query_sql};")

        lines.append("BEGIN")
        for s in r.body.statements:
            lines.append(self._emit_postgres_stmt(s, indent=4))

        if r.body.exception_section:
            lines.append("EXCEPTION")
            for h in r.body.exception_section.handlers:
                exc_list = ", ".join(self._map_exception_names(h.exception_names, Dialect.POSTGRES))
                lines.append(f"    WHEN {exc_list} THEN")
                for s in h.statements:
                    lines.append(self._emit_postgres_stmt(s, indent=8))
            if r.body.exception_section.others_handler:
                lines.append("    WHEN OTHERS THEN")
                for s in r.body.exception_section.others_handler:
                    lines.append(self._emit_postgres_stmt(s, indent=8))

        lines.append("END;")
        lines.append("$$;")
        return "\n".join(lines)

    def _emit_postgres_trigger(self, t: TriggerDefinition) -> str:
        func_name = f"fn_{t.name}"
        lines: list[str] = []

        lines.append(f"CREATE OR REPLACE FUNCTION {func_name}()")
        lines.append("RETURNS trigger")
        lines.append("LANGUAGE plpgsql")
        lines.append("AS $$")
        if t.body.declarations:
            lines.append("DECLARE")
            for d in t.body.declarations:
                if isinstance(d, VariableDecl):
                    lines.append(f"    {d.name} {self._map_type(d.data_type, Dialect.POSTGRES)};")
        lines.append("BEGIN")
        for s in t.body.statements:
            lines.append(self._emit_postgres_stmt(s, indent=4, is_trigger=True))
        lines.append("    RETURN NEW;")
        lines.append("END;")
        lines.append("$$;")
        lines.append("")

        events_str = " OR ".join(t.events)
        row_str = "FOR EACH ROW" if t.for_each_row else "FOR EACH STATEMENT"
        when_str = f"WHEN ({t.when_condition}) " if t.when_condition else ""
        if t.or_replace:
            lines.append(f"DROP TRIGGER IF EXISTS {t.name} ON {t.table_name};")
        trigger_sql = (
            f"CREATE TRIGGER {t.name} {t.timing} {events_str} ON {t.table_name} "
            f"{row_str} {when_str}EXECUTE FUNCTION {func_name}();"
        )
        lines.append(trigger_sql)
        return "\n".join(lines)



    def _emit_postgres_stmt(self, s: Any, indent: int = 4, is_trigger: bool = False) -> str:
        sp = " " * indent
        if isinstance(s, AssignmentStmt):
            target = self._normalize_pseudo_record(s.target, Dialect.POSTGRES) if is_trigger else s.target
            expr = self._normalize_expr(s.expression, Dialect.POSTGRES, is_trigger)
            return f"{sp}{target} := {expr};"
        elif isinstance(s, SelectIntoStmt):
            exprs = ", ".join(self._normalize_expr(e, Dialect.POSTGRES, is_trigger) for e in s.select_expressions)
            vars_ = ", ".join(s.into_variables)
            where_ = f" WHERE {self._normalize_expr(s.where_clause, Dialect.POSTGRES, is_trigger)}" if s.where_clause else ""
            return f"{sp}SELECT {exprs} INTO {vars_} FROM {s.from_clause}{where_};"  # noqa: S608
        elif isinstance(s, IfStmt):
            lines: list[str] = []
            for i, b in enumerate(s.branches):
                kw = "IF" if i == 0 else "ELSIF"
                cond = self._normalize_expr(b.condition, Dialect.POSTGRES, is_trigger)
                lines.append(f"{sp}{kw} {cond} THEN")
                for substmt in b.statements:
                    lines.append(self._emit_postgres_stmt(substmt, indent + 4, is_trigger))
            if s.else_statements:
                lines.append(f"{sp}ELSE")
                for substmt in s.else_statements:
                    lines.append(self._emit_postgres_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END IF;")
            return "\n".join(lines)
        elif isinstance(s, WhileStmt):
            cond = self._normalize_expr(s.condition, Dialect.POSTGRES, is_trigger)
            lines = [f"{sp}WHILE {cond} LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_postgres_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, ForRangeLoopStmt):
            rev = "REVERSE " if s.reverse else ""
            lines = [f"{sp}FOR {s.loop_var} IN {rev}{s.lower_bound}..{s.upper_bound} LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_postgres_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, CursorForLoopStmt):
            query = f"({s.cursor_or_query})" if s.is_raw_query else s.cursor_or_query
            lines = [f"{sp}FOR {s.record_var} IN {query} LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_postgres_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, SimpleLoopStmt):
            lines = [f"{sp}LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_postgres_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, ExitWhenStmt):
            cond = f" WHEN {self._normalize_expr(s.condition, Dialect.POSTGRES, is_trigger)}" if s.condition else ""
            return f"{sp}EXIT{cond};"
        elif isinstance(s, ReturnStmt):
            expr = f" {self._normalize_expr(s.expression, Dialect.POSTGRES, is_trigger)}" if s.expression else ""
            return f"{sp}RETURN{expr};"
        elif isinstance(s, CursorOpenStmt):
            return f"{sp}OPEN {s.cursor_name};"
        elif isinstance(s, CursorFetchStmt):
            vars_ = ", ".join(s.into_variables)
            return f"{sp}FETCH {s.cursor_name} INTO {vars_};"
        elif isinstance(s, CursorCloseStmt):
            return f"{sp}CLOSE {s.cursor_name};"
        elif isinstance(s, RaiseStmt):
            if s.error_message:
                return f"{sp}RAISE EXCEPTION {s.error_message};"
            if s.exception_name:
                return f"{sp}RAISE EXCEPTION '%', {s.exception_name!r};"
            return f"{sp}RAISE;"
        elif isinstance(s, ExecuteImmediateStmt):
            into_ = f" INTO {', '.join(s.into_variables)}" if s.into_variables else ""
            using_ = f" USING {', '.join(s.using_parameters)}" if s.using_parameters else ""
            return f"{sp}EXECUTE {s.query_expr}{into_}{using_};"
        elif isinstance(s, TransactionStmt):
            if s.action == "COMMIT":
                return f"{sp}COMMIT;"
            elif s.action == "ROLLBACK":
                return f"{sp}ROLLBACK;"
            elif s.action == "SAVEPOINT":
                return f"{sp}SAVEPOINT {s.savepoint_name};"
            elif s.action == "ROLLBACK_TO":
                return f"{sp}ROLLBACK TO SAVEPOINT {s.savepoint_name};"
        elif isinstance(s, DmlStmt):
            return f"{sp}{self._normalize_expr(s.sql, Dialect.POSTGRES, is_trigger)}"
        elif isinstance(s, RawStmt):
            return f"{sp}{self._normalize_expr(s.text, Dialect.POSTGRES, is_trigger)}"
        return f"{sp}NULL;"

    def _emit_postgres_package(self, pkg: PackageDefinition) -> str:
        """Lower Oracle package into PostgreSQL schema and routines with session state."""
        lines: list[str] = [
            f"-- ============================================================================",
            f"-- Lowered Package: {pkg.name} (PostgreSQL Schema Architecture)",
            f"-- ============================================================================",
            f"CREATE SCHEMA IF NOT EXISTS {pkg.name};",
            "",
        ]

        # 1. State Variables Management (Session Config getters/setters)
        all_vars: list[VariableDecl] = []
        if pkg.spec:
            all_vars.extend(pkg.spec.variables)
        if pkg.body:
            all_vars.extend(pkg.body.private_variables)

        if all_vars:
            lines.append(f"-- Package State Management for {pkg.name}")
            for v in all_vars:
                pg_type = self._map_type(v.data_type, Dialect.POSTGRES)
                lines.append(
                    f"CREATE OR REPLACE FUNCTION {pkg.name}.get_{v.name}() RETURNS {pg_type} AS $$\n"
                    f"BEGIN\n"
                    f"    RETURN current_setting('{pkg.name}.{v.name}', true)::{pg_type};\n"
                    f"END;\n"
                    f"$$ LANGUAGE plpgsql;\n"
                )
                lines.append(
                    f"CREATE OR REPLACE FUNCTION {pkg.name}.set_{v.name}(p_val {pg_type}) RETURNS void AS $$\n"
                    f"BEGIN\n"
                    f"    PERFORM set_config('{pkg.name}.{v.name}', p_val::text, false);\n"
                    f"END;\n"
                    f"$$ LANGUAGE plpgsql;\n"
                )

        # 2. Package Routines
        routines = pkg.body.routines if pkg.body and pkg.body.routines else (pkg.spec.routine_signatures if pkg.spec else [])
        for r in routines:
            r.schema = pkg.name
            r.or_replace = True
            lines.append(self._emit_postgres_routine(r))
            lines.append("")

        # 3. Initialization Block
        if pkg.body and pkg.body.initialization_statements:
            lines.append(f"-- Package Initialization for {pkg.name}")
            init_lines = [
                f"CREATE OR REPLACE FUNCTION {pkg.name}._init() RETURNS void AS $$",
                "BEGIN",
            ]
            for s in pkg.body.initialization_statements:
                init_lines.append(self._emit_postgres_stmt(s, indent=4))
            init_lines.append("END;")
            init_lines.append("$$ LANGUAGE plpgsql;")
            lines.append("\n".join(init_lines))
            lines.append(f"SELECT {pkg.name}._init();")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Oracle / DM8 Emitters
    # -------------------------------------------------------------------------
    def _emit_oracle_routine(self, r: RoutineDefinition) -> str:
        lines: list[str] = []
        kind_str = "PROCEDURE" if r.kind == RoutineKind.PROCEDURE else "FUNCTION"
        replace_str = "OR REPLACE " if r.or_replace else ""
        obj_name = f"{r.schema}.{r.name}" if r.schema else r.name

        param_strs: list[str] = []
        for p in r.parameters:
            mode_str = f"{p.mode.value} " if p.mode != ParamMode.IN else ""
            default_str = f" := {p.default_expr}" if p.default_expr else ""
            param_strs.append(f"{p.name} {mode_str}{self._map_type(p.data_type, Dialect.ORACLE)}{default_str}")

        lines.append(f"CREATE {replace_str}{kind_str} {obj_name}({', '.join(param_strs)})")
        if r.kind == RoutineKind.FUNCTION and r.return_type:
            lines.append(f"RETURN {self._map_type(r.return_type, Dialect.ORACLE)}")

        lines.append("IS")
        if r.body.is_autonomous:
            lines.append("    PRAGMA AUTONOMOUS_TRANSACTION;")

        for d in r.body.declarations:
            if isinstance(d, VariableDecl):
                c_str = "CONSTANT " if d.is_constant else ""
                def_str = f" := {d.default_expr}" if d.default_expr else ""
                lines.append(f"    {d.name} {c_str}{self._map_type(d.data_type, Dialect.ORACLE)}{def_str};")
            elif isinstance(d, CursorDecl):
                lines.append(f"    CURSOR {d.name} IS {d.query_sql};")

        lines.append("BEGIN")
        for s in r.body.statements:
            lines.append(self._emit_oracle_stmt(s, indent=4))

        if r.body.exception_section:
            lines.append("EXCEPTION")
            for h in r.body.exception_section.handlers:
                exc_list = " OR ".join(self._map_exception_names(h.exception_names, Dialect.ORACLE))
                lines.append(f"    WHEN {exc_list} THEN")
                for s in h.statements:
                    lines.append(self._emit_oracle_stmt(s, indent=8))
            if r.body.exception_section.others_handler:
                lines.append("    WHEN OTHERS THEN")
                for s in r.body.exception_section.others_handler:
                    lines.append(self._emit_oracle_stmt(s, indent=8))

        lines.append("END;")
        return "\n".join(lines)

    def _emit_oracle_trigger(self, t: TriggerDefinition) -> str:
        lines: list[str] = []
        rep_str = "OR REPLACE " if t.or_replace else ""
        events_str = " OR ".join(t.events)
        row_str = "FOR EACH ROW" if t.for_each_row else ""
        when_str = f"WHEN ({t.when_condition}) " if t.when_condition else ""

        lines.append(f"CREATE {rep_str}TRIGGER {t.name}")
        lines.append(f"{t.timing} {events_str} ON {t.table_name}")
        if row_str:
            lines.append(row_str)
        if when_str:
            lines.append(when_str)
        lines.append("IS")
        for d in t.body.declarations:
            if isinstance(d, VariableDecl):
                lines.append(f"    {d.name} {self._map_type(d.data_type, Dialect.ORACLE)};")
        lines.append("BEGIN")
        for s in t.body.statements:
            lines.append(self._emit_oracle_stmt(s, indent=4, is_trigger=True))
        lines.append("END;")
        return "\n".join(lines)

    def _emit_oracle_stmt(self, s: Any, indent: int = 4, is_trigger: bool = False) -> str:
        sp = " " * indent
        if isinstance(s, AssignmentStmt):
            target = self._normalize_pseudo_record(s.target, Dialect.ORACLE) if is_trigger else s.target
            return f"{sp}{target} := {s.expression};"
        elif isinstance(s, SelectIntoStmt):
            exprs = ", ".join(s.select_expressions)
            vars_ = ", ".join(s.into_variables)
            where_ = f" WHERE {s.where_clause}" if s.where_clause else ""
            return f"{sp}SELECT {exprs} INTO {vars_} FROM {s.from_clause}{where_};"  # noqa: S608
        elif isinstance(s, IfStmt):
            lines: list[str] = []
            for i, b in enumerate(s.branches):
                kw = "IF" if i == 0 else "ELSIF"
                lines.append(f"{sp}{kw} {b.condition} THEN")
                for substmt in b.statements:
                    lines.append(self._emit_oracle_stmt(substmt, indent + 4, is_trigger))
            if s.else_statements:
                lines.append(f"{sp}ELSE")
                for substmt in s.else_statements:
                    lines.append(self._emit_oracle_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END IF;")
            return "\n".join(lines)
        elif isinstance(s, WhileStmt):
            lines = [f"{sp}WHILE {s.condition} LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_oracle_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, ForRangeLoopStmt):
            rev = "REVERSE " if s.reverse else ""
            lines = [f"{sp}FOR {s.loop_var} IN {rev}{s.lower_bound}..{s.upper_bound} LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_oracle_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, CursorForLoopStmt):
            query = f"({s.cursor_or_query})" if s.is_raw_query else s.cursor_or_query
            lines = [f"{sp}FOR {s.record_var} IN {query} LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_oracle_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, SimpleLoopStmt):
            lines = [f"{sp}LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_oracle_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP;")
            return "\n".join(lines)
        elif isinstance(s, ExitWhenStmt):
            cond = f" WHEN {s.condition}" if s.condition else ""
            return f"{sp}EXIT{cond};"
        elif isinstance(s, ReturnStmt):
            expr = f" {s.expression}" if s.expression else ""
            return f"{sp}RETURN{expr};"
        elif isinstance(s, CursorOpenStmt):
            return f"{sp}OPEN {s.cursor_name};"
        elif isinstance(s, CursorFetchStmt):
            vars_ = ", ".join(s.into_variables)
            return f"{sp}FETCH {s.cursor_name} INTO {vars_};"
        elif isinstance(s, CursorCloseStmt):
            return f"{sp}CLOSE {s.cursor_name};"
        elif isinstance(s, RaiseStmt):
            if s.error_code and s.error_message:
                return f"{sp}RAISE_APPLICATION_ERROR({s.error_code}, {s.error_message});"
            if s.exception_name:
                return f"{sp}RAISE {s.exception_name};"
            return f"{sp}RAISE;"
        elif isinstance(s, ExecuteImmediateStmt):
            into_ = f" INTO {', '.join(s.into_variables)}" if s.into_variables else ""
            using_ = f" USING {', '.join(s.using_parameters)}" if s.using_parameters else ""
            return f"{sp}EXECUTE IMMEDIATE {s.query_expr}{into_}{using_};"
        elif isinstance(s, TransactionStmt):
            if s.action == "COMMIT":
                return f"{sp}COMMIT;"
            elif s.action == "ROLLBACK":
                return f"{sp}ROLLBACK;"
            elif s.action == "SAVEPOINT":
                return f"{sp}SAVEPOINT {s.savepoint_name};"
            elif s.action == "ROLLBACK_TO":
                return f"{sp}ROLLBACK TO {s.savepoint_name};"
        elif isinstance(s, DmlStmt):
            return f"{sp}{s.sql}"
        elif isinstance(s, RawStmt):
            return f"{sp}{s.text}"
        return f"{sp}NULL;"

    def _emit_oracle_package(self, pkg: PackageDefinition) -> str:
        """Emit native Oracle / DM8 package specification and body."""
        lines: list[str] = []
        replace_str = "OR REPLACE " if pkg.or_replace else ""
        obj_name = f"{pkg.schema}.{pkg.name}" if pkg.schema else pkg.name

        if pkg.spec:
            lines.append(f"CREATE {replace_str}PACKAGE {obj_name} IS")
            for v in pkg.spec.variables:
                c_str = "CONSTANT " if v.is_constant else ""
                def_str = f" := {v.default_expr}" if v.default_expr else ""
                lines.append(f"    {v.name} {c_str}{self._map_type(v.data_type, Dialect.ORACLE)}{def_str};")
            for r in pkg.spec.routine_signatures:
                kind_str = "PROCEDURE" if r.kind == RoutineKind.PROCEDURE else "FUNCTION"
                param_strs: list[str] = []
                for p in r.parameters:
                    mode_str = f"{p.mode.value} " if p.mode != ParamMode.IN else ""
                    default_str = f" := {p.default_expr}" if p.default_expr else ""
                    param_strs.append(f"{p.name} {mode_str}{self._map_type(p.data_type, Dialect.ORACLE)}{default_str}")
                ret_str = f" RETURN {self._map_type(r.return_type, Dialect.ORACLE)}" if r.return_type else ""
                lines.append(f"    {kind_str} {r.name}({', '.join(param_strs)}){ret_str};")
            lines.append(f"END {pkg.name};")
            lines.append("/")
            lines.append("")

        if pkg.body:
            lines.append(f"CREATE {replace_str}PACKAGE BODY {obj_name} IS")
            for v in pkg.body.private_variables:
                c_str = "CONSTANT " if v.is_constant else ""
                def_str = f" := {v.default_expr}" if v.default_expr else ""
                lines.append(f"    {v.name} {c_str}{self._map_type(v.data_type, Dialect.ORACLE)}{def_str};")
            for r in pkg.body.routines:
                r_sql = self._emit_oracle_routine(r)
                r_sql = re.sub(r"^CREATE\s+(?:OR\s+REPLACE\s+)?", "", r_sql.strip(), flags=re.IGNORECASE)
                lines.append(r_sql)
                lines.append("")
            if pkg.body.initialization_statements:
                lines.append("BEGIN")
                for s in pkg.body.initialization_statements:
                    lines.append(self._emit_oracle_stmt(s, indent=4))
            lines.append(f"END {pkg.name};")
            lines.append("/")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # SQL Server (T-SQL) Emitters
    # -------------------------------------------------------------------------
    def _emit_tsql_routine(self, r: RoutineDefinition) -> str:
        lines: list[str] = []
        kind_str = "PROCEDURE" if r.kind == RoutineKind.PROCEDURE else "FUNCTION"
        obj_name = f"{r.schema}.{r.name}" if r.schema else r.name

        param_strs: list[str] = []
        for p in r.parameters:
            name_ = p.name if p.name.startswith("@") else f"@{p.name}"
            mode_str = " OUTPUT" if p.mode in (ParamMode.OUT, ParamMode.INOUT) else ""
            default_str = f" = {p.default_expr}" if p.default_expr else ""
            param_strs.append(f"{name_} {self._map_type(p.data_type, Dialect.TSQL)}{default_str}{mode_str}")

        lines.append(f"CREATE {kind_str} {obj_name}")
        if param_strs:
            lines.append("    " + ",\n    ".join(param_strs))
        lines.append("AS")
        lines.append("BEGIN")
        lines.append("    SET NOCOUNT ON;")

        if r.body.is_autonomous:
            lines.append("    -- [Autonomous Transaction]: Converted to independent transaction scope")

        for d in r.body.declarations:
            if isinstance(d, VariableDecl):
                v_name = d.name if d.name.startswith("@") else f"@{d.name}"
                def_str = f" = {self._normalize_expr(d.default_expr, Dialect.TSQL)}" if d.default_expr else ""
                lines.append(f"    DECLARE {v_name} {self._map_type(d.data_type, Dialect.TSQL)}{def_str};")
            elif isinstance(d, CursorDecl):
                c_name = d.name if d.name.startswith("@") else f"@{d.name}"
                lines.append(f"    DECLARE {c_name} CURSOR LOCAL FAST_FORWARD FOR {d.query_sql};")

        has_exc = bool(r.body.exception_section)
        indent = 8 if has_exc else 4
        if has_exc:
            lines.append("    BEGIN TRY")

        for s in r.body.statements:
            lines.append(self._emit_tsql_stmt(s, indent=indent))

        if has_exc:
            lines.append("    END TRY")
            lines.append("    BEGIN CATCH")
            if r.body.exception_section and r.body.exception_section.others_handler:
                for s in r.body.exception_section.others_handler:
                    lines.append(self._emit_tsql_stmt(s, indent=8))
            else:
                lines.append("        THROW;")
            lines.append("    END CATCH")

        lines.append("END;")
        return "\n".join(lines)

    def _emit_tsql_trigger(self, t: TriggerDefinition) -> str:
        lines: list[str] = []
        events_str = ", ".join(t.events)
        lines.append(f"CREATE TRIGGER {t.name}")
        lines.append(f"ON {t.table_name}")
        lines.append(f"{t.timing} {events_str}")
        lines.append("AS")
        lines.append("BEGIN")
        lines.append("    SET NOCOUNT ON;")
        for s in t.body.statements:
            lines.append(self._emit_tsql_stmt(s, indent=4, is_trigger=True))
        lines.append("END;")
        return "\n".join(lines)

    def _emit_tsql_stmt(self, s: Any, indent: int = 4, is_trigger: bool = False) -> str:
        sp = " " * indent
        if isinstance(s, AssignmentStmt):
            target = s.target if s.target.startswith("@") else f"@{s.target}"
            expr = self._normalize_expr(s.expression, Dialect.TSQL, is_trigger)
            return f"{sp}SET {target} = {expr};"
        elif isinstance(s, SelectIntoStmt):
            vars_ = ", ".join(v if v.startswith("@") else f"@{v}" for v in s.into_variables)
            exprs = ", ".join(f"{v} = {self._normalize_expr(e, Dialect.TSQL, is_trigger)}" for v, e in zip(vars_.split(", "), s.select_expressions, strict=False))
            where_ = f" WHERE {self._normalize_expr(s.where_clause, Dialect.TSQL, is_trigger)}" if s.where_clause else ""
            return f"{sp}SELECT {exprs} FROM {s.from_clause}{where_};"  # noqa: S608
        elif isinstance(s, IfStmt):
            lines: list[str] = []
            for i, b in enumerate(s.branches):
                kw = "IF" if i == 0 else "ELSE IF"
                cond = self._normalize_expr(b.condition, Dialect.TSQL, is_trigger)
                lines.append(f"{sp}{kw} {cond}")
                lines.append(f"{sp}BEGIN")
                for substmt in b.statements:
                    lines.append(self._emit_tsql_stmt(substmt, indent + 4, is_trigger))
                lines.append(f"{sp}END")
            if s.else_statements:
                lines.append(f"{sp}ELSE")
                lines.append(f"{sp}BEGIN")
                for substmt in s.else_statements:
                    lines.append(self._emit_tsql_stmt(substmt, indent + 4, is_trigger))
                lines.append(f"{sp}END")
            return "\n".join(lines)
        elif isinstance(s, WhileStmt):
            cond = self._normalize_expr(s.condition, Dialect.TSQL, is_trigger)
            lines = [f"{sp}WHILE {cond}", f"{sp}BEGIN"]
            for substmt in s.statements:
                lines.append(self._emit_tsql_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END")
            return "\n".join(lines)
        elif isinstance(s, ForRangeLoopStmt):
            v = s.loop_var if s.loop_var.startswith("@") else f"@{s.loop_var}"
            step = "- 1" if s.reverse else "+ 1"
            cmp_op = ">=" if s.reverse else "<="
            start_val = s.upper_bound if s.reverse else s.lower_bound
            end_val = s.lower_bound if s.reverse else s.upper_bound
            lines = [
                f"{sp}SET {v} = {start_val};",
                f"{sp}WHILE {v} {cmp_op} {end_val}",
                f"{sp}BEGIN",
            ]
            for substmt in s.statements:
                lines.append(self._emit_tsql_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}    SET {v} = {v} {step};")
            lines.append(f"{sp}END")
            return "\n".join(lines)
        elif isinstance(s, SimpleLoopStmt):
            lines = [f"{sp}WHILE 1 = 1", f"{sp}BEGIN"]
            for substmt in s.statements:
                lines.append(self._emit_tsql_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END")
            return "\n".join(lines)
        elif isinstance(s, ExitWhenStmt):
            cond = self._normalize_expr(s.condition, Dialect.TSQL, is_trigger)
            if cond:
                return f"{sp}IF {cond} BREAK;"
            return f"{sp}BREAK;"
        elif isinstance(s, ReturnStmt):
            expr = f" {self._normalize_expr(s.expression, Dialect.TSQL, is_trigger)}" if s.expression else ""
            return f"{sp}RETURN{expr};"
        elif isinstance(s, CursorOpenStmt):
            c_name = s.cursor_name if s.cursor_name.startswith("@") else f"@{s.cursor_name}"
            return f"{sp}OPEN {c_name};"
        elif isinstance(s, CursorFetchStmt):
            c_name = s.cursor_name if s.cursor_name.startswith("@") else f"@{s.cursor_name}"
            vars_ = ", ".join(v if v.startswith("@") else f"@{v}" for v in s.into_variables)
            return f"{sp}FETCH NEXT FROM {c_name} INTO {vars_};"
        elif isinstance(s, CursorCloseStmt):
            c_name = s.cursor_name if s.cursor_name.startswith("@") else f"@{s.cursor_name}"
            return f"{sp}CLOSE {c_name}; DEALLOCATE {c_name};"
        elif isinstance(s, RaiseStmt):
            code = s.error_code or 50000
            msg = s.error_message or "'User error'"
            return f"{sp}THROW {code}, {msg}, 1;"
        elif isinstance(s, ExecuteImmediateStmt):
            return f"{sp}EXEC sp_executesql {s.query_expr};"
        elif isinstance(s, TransactionStmt):
            if s.action == "COMMIT":
                return f"{sp}COMMIT TRANSACTION;"
            elif s.action == "ROLLBACK":
                return f"{sp}ROLLBACK TRANSACTION;"
            elif s.action == "SAVEPOINT":
                return f"{sp}SAVE TRANSACTION {s.savepoint_name};"
            elif s.action == "ROLLBACK_TO":
                return f"{sp}ROLLBACK TRANSACTION {s.savepoint_name};"
        elif isinstance(s, DmlStmt):
            return f"{sp}{self._normalize_expr(s.sql, Dialect.TSQL, is_trigger)}"
        elif isinstance(s, RawStmt):
            return f"{sp}{self._normalize_expr(s.text, Dialect.TSQL, is_trigger)}"
        return f"{sp}-- noop"

    def _emit_tsql_package(self, pkg: PackageDefinition) -> str:
        """Lower Oracle package into SQL Server schema-scoped / prefixed procedures."""
        lines: list[str] = [
            f"-- ============================================================================",
            f"-- Lowered Package: {pkg.name} (T-SQL Prefixed Architecture)",
            f"-- ============================================================================",
            "",
        ]
        routines = pkg.body.routines if pkg.body and pkg.body.routines else (pkg.spec.routine_signatures if pkg.spec else [])
        for r in routines:
            r_copy = RoutineDefinition(
                name=f"{pkg.name}_{r.name}",
                kind=r.kind,
                parameters=r.parameters,
                return_type=r.return_type,
                body=r.body,
                schema=pkg.schema or "dbo",
                or_replace=r.or_replace,
            )
            lines.append(self._emit_tsql_routine(r_copy))
            lines.append("GO")
            lines.append("")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # MySQL Emitters
    # -------------------------------------------------------------------------
    def _emit_mysql_routine(self, r: RoutineDefinition) -> str:
        lines: list[str] = []
        kind_str = "PROCEDURE" if r.kind == RoutineKind.PROCEDURE else "FUNCTION"
        obj_name = f"`{r.schema}`.`{r.name}`" if r.schema else f"`{r.name}`"

        param_strs: list[str] = []
        for p in r.parameters:
            mode_str = f"{p.mode.value} " if r.kind == RoutineKind.PROCEDURE else ""
            param_strs.append(f"{mode_str}`{p.name}` {self._map_type(p.data_type, Dialect.MYSQL)}")

        lines.append(f"DROP {kind_str} IF EXISTS {obj_name};")
        lines.append(f"CREATE {kind_str} {obj_name}({', '.join(param_strs)})")
        if r.kind == RoutineKind.FUNCTION and r.return_type:
            lines.append(f"RETURNS {self._map_type(r.return_type, Dialect.MYSQL)}")
            lines.append("DETERMINISTIC")

        lines.append("BEGIN")

        if r.body.is_autonomous:
            lines.append("    -- [Autonomous Transaction]: Converted to independent transaction scope")

        for d in r.body.declarations:
            if isinstance(d, VariableDecl):
                def_str = f" DEFAULT {self._normalize_expr(d.default_expr, Dialect.MYSQL)}" if d.default_expr else ""
                lines.append(f"    DECLARE `{d.name}` {self._map_type(d.data_type, Dialect.MYSQL)}{def_str};")
            elif isinstance(d, CursorDecl):
                lines.append(f"    DECLARE `{d.name}` CURSOR FOR {d.query_sql};")

        if r.body.exception_section:
            lines.append("    DECLARE EXIT HANDLER FOR SQLEXCEPTION")
            lines.append("    BEGIN")
            if r.body.exception_section.others_handler:
                for s in r.body.exception_section.others_handler:
                    lines.append(self._emit_mysql_stmt(s, indent=8))
            else:
                lines.append("        RESIGNAL;")
            lines.append("    END;")

        for s in r.body.statements:
            lines.append(self._emit_mysql_stmt(s, indent=4))

        lines.append("END;")
        return "\n".join(lines)

    def _emit_mysql_trigger(self, t: TriggerDefinition) -> str:
        lines: list[str] = []
        events_str = t.events[0] if t.events else "INSERT"
        lines.append(f"DROP TRIGGER IF EXISTS `{t.name}`;")
        lines.append(f"CREATE TRIGGER `{t.name}`")
        lines.append(f"{t.timing} {events_str} ON `{t.table_name}`")
        lines.append("FOR EACH ROW")
        lines.append("BEGIN")
        for s in t.body.statements:
            lines.append(self._emit_mysql_stmt(s, indent=4, is_trigger=True))
        lines.append("END;")
        return "\n".join(lines)

    def _emit_mysql_stmt(self, s: Any, indent: int = 4, is_trigger: bool = False) -> str:
        sp = " " * indent
        if isinstance(s, AssignmentStmt):
            target = self._normalize_pseudo_record(s.target, Dialect.MYSQL) if is_trigger else f"`{s.target}`"
            expr = self._normalize_expr(s.expression, Dialect.MYSQL, is_trigger)
            return f"{sp}SET {target} = {expr};"
        elif isinstance(s, SelectIntoStmt):
            exprs = ", ".join(self._normalize_expr(e, Dialect.MYSQL, is_trigger) for e in s.select_expressions)
            vars_ = ", ".join(f"`{v}`" for v in s.into_variables)
            where_ = f" WHERE {self._normalize_expr(s.where_clause, Dialect.MYSQL, is_trigger)}" if s.where_clause else ""
            return f"{sp}SELECT {exprs} INTO {vars_} FROM {s.from_clause}{where_};"  # noqa: S608
        elif isinstance(s, IfStmt):
            lines: list[str] = []
            for i, b in enumerate(s.branches):
                kw = "IF" if i == 0 else "ELSEIF"
                cond = self._normalize_expr(b.condition, Dialect.MYSQL, is_trigger)
                lines.append(f"{sp}{kw} {cond} THEN")
                for substmt in b.statements:
                    lines.append(self._emit_mysql_stmt(substmt, indent + 4, is_trigger))
            if s.else_statements:
                lines.append(f"{sp}ELSE")
                for substmt in s.else_statements:
                    lines.append(self._emit_mysql_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END IF;")
            return "\n".join(lines)
        elif isinstance(s, WhileStmt):
            cond = self._normalize_expr(s.condition, Dialect.MYSQL, is_trigger)
            lines = [f"{sp}WHILE {cond} DO"]
            for substmt in s.statements:
                lines.append(self._emit_mysql_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END WHILE;")
            return "\n".join(lines)
        elif isinstance(s, SimpleLoopStmt):
            lines = [f"{sp}simple_loop: LOOP"]
            for substmt in s.statements:
                lines.append(self._emit_mysql_stmt(substmt, indent + 4, is_trigger))
            lines.append(f"{sp}END LOOP simple_loop;")
            return "\n".join(lines)
        elif isinstance(s, ExitWhenStmt):
            cond = self._normalize_expr(s.condition, Dialect.MYSQL, is_trigger)
            if cond:
                return f"{sp}IF {cond} THEN LEAVE simple_loop; END IF;"
            return f"{sp}LEAVE simple_loop;"
        elif isinstance(s, ReturnStmt):
            expr = f" {self._normalize_expr(s.expression, Dialect.MYSQL, is_trigger)}" if s.expression else ""
            return f"{sp}RETURN{expr};"
        elif isinstance(s, CursorOpenStmt):
            return f"{sp}OPEN `{s.cursor_name}`;"
        elif isinstance(s, CursorFetchStmt):
            vars_ = ", ".join(f"`{v}`" for v in s.into_variables)
            return f"{sp}FETCH `{s.cursor_name}` INTO {vars_};"
        elif isinstance(s, CursorCloseStmt):
            return f"{sp}CLOSE `{s.cursor_name}`;"
        elif isinstance(s, RaiseStmt):
            msg = s.error_message or "'Error'"
            return f"{sp}SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = {msg};"
        elif isinstance(s, ExecuteImmediateStmt):
            lines = [
                f"{sp}SET @dyn_stmt = {s.query_expr};",
                f"{sp}PREPARE stmt FROM @dyn_stmt;",
                f"{sp}EXECUTE stmt;",
                f"{sp}DEALLOCATE PREPARE stmt;",
            ]
            return "\n".join(lines)
        elif isinstance(s, TransactionStmt):
            if s.action == "COMMIT":
                return f"{sp}COMMIT;"
            elif s.action == "ROLLBACK":
                return f"{sp}ROLLBACK;"
            elif s.action == "SAVEPOINT":
                return f"{sp}SAVEPOINT {s.savepoint_name};"
            elif s.action == "ROLLBACK_TO":
                return f"{sp}ROLLBACK TO SAVEPOINT {s.savepoint_name};"
        elif isinstance(s, DmlStmt):
            return f"{sp}{self._normalize_expr(s.sql, Dialect.MYSQL, is_trigger)}"
        elif isinstance(s, RawStmt):
            return f"{sp}{self._normalize_expr(s.text, Dialect.MYSQL, is_trigger)}"
        return f"{sp}-- noop"

    def _emit_mysql_package(self, pkg: PackageDefinition) -> str:
        """Lower Oracle package into MySQL prefixed procedures with session variable state."""
        lines: list[str] = [
            f"-- ============================================================================",
            f"-- Lowered Package: {pkg.name} (MySQL / TiDB Prefixed Architecture)",
            f"-- ============================================================================",
            "",
        ]
        all_vars: list[VariableDecl] = []
        if pkg.spec:
            all_vars.extend(pkg.spec.variables)
        if pkg.body:
            all_vars.extend(pkg.body.private_variables)

        if all_vars:
            lines.append(f"-- Session variables for package {pkg.name}")
            for v in all_vars:
                init_val = v.default_expr or "NULL"
                lines.append(f"SET @_{pkg.name}__{v.name} = {init_val};")
            lines.append("")

        routines = pkg.body.routines if pkg.body and pkg.body.routines else (pkg.spec.routine_signatures if pkg.spec else [])
        for r in routines:
            r_copy = RoutineDefinition(
                name=f"{pkg.name}__{r.name}",
                kind=r.kind,
                parameters=r.parameters,
                return_type=r.return_type,
                body=r.body,
                schema=pkg.schema,
                or_replace=r.or_replace,
            )
            lines.append(self._emit_mysql_routine(r_copy))
            lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Mapping Utilities
    # -------------------------------------------------------------------------
    def _map_type(self, type_str: str, target_dialect: Dialect) -> str:
        t_up = type_str.strip().upper()
        if "%TYPE" in t_up or "%ROWTYPE" in t_up:
            if target_dialect == Dialect.POSTGRES:
                return type_str.replace(":", "")
            elif target_dialect == Dialect.ORACLE:
                return type_str
            return "VARCHAR(255)"

        mapping: dict[str, dict[Dialect, str]] = {
            "INT": {
                Dialect.POSTGRES: "INTEGER",
                Dialect.ORACLE: "NUMBER(10)",
                Dialect.TSQL: "INT",
                Dialect.MYSQL: "INT",
            },
            "INTEGER": {
                Dialect.POSTGRES: "INTEGER",
                Dialect.ORACLE: "NUMBER(10)",
                Dialect.TSQL: "INT",
                Dialect.MYSQL: "INT",
            },
            "BIGINT": {
                Dialect.POSTGRES: "BIGINT",
                Dialect.ORACLE: "NUMBER(19)",
                Dialect.TSQL: "BIGINT",
                Dialect.MYSQL: "BIGINT",
            },
            "VARCHAR": {
                Dialect.POSTGRES: "VARCHAR(255)",
                Dialect.ORACLE: "VARCHAR2(255)",
                Dialect.TSQL: "NVARCHAR(255)",
                Dialect.MYSQL: "VARCHAR(255)",
            },
            "TEXT": {
                Dialect.POSTGRES: "TEXT",
                Dialect.ORACLE: "CLOB",
                Dialect.TSQL: "NVARCHAR(MAX)",
                Dialect.MYSQL: "LONGTEXT",
            },
            "DECIMAL": {
                Dialect.POSTGRES: "NUMERIC",
                Dialect.ORACLE: "NUMBER",
                Dialect.TSQL: "DECIMAL",
                Dialect.MYSQL: "DECIMAL",
            },
            "NUMBER": {
                Dialect.POSTGRES: "NUMERIC",
                Dialect.ORACLE: "NUMBER",
                Dialect.TSQL: "NUMERIC",
                Dialect.MYSQL: "DECIMAL",
            },
            "BOOLEAN": {
                Dialect.POSTGRES: "BOOLEAN",
                Dialect.ORACLE: "NUMBER(1)",
                Dialect.TSQL: "BIT",
                Dialect.MYSQL: "TINYINT(1)",
            },
            "TIMESTAMP": {
                Dialect.POSTGRES: "TIMESTAMP",
                Dialect.ORACLE: "TIMESTAMP",
                Dialect.TSQL: "DATETIME2",
                Dialect.MYSQL: "DATETIME",
            },
        }
        for k, v in mapping.items():
            if t_up.startswith(k):
                m_param = re.search(r"\((.*?)\)", t_up)
                if m_param:
                    base = v.get(target_dialect, k).split("(")[0]
                    return f"{base}({m_param.group(1)})"
                return v.get(target_dialect, k)
        return type_str

    def _map_exception_names(self, names: list[str], target_dialect: Dialect) -> list[str]:
        results: list[str] = []
        for n in names:
            nu = n.upper()
            if target_dialect == Dialect.POSTGRES:
                if nu == "NO_DATA_FOUND":
                    results.append("NO_DATA_FOUND")
                elif nu == "TOO_MANY_ROWS":
                    results.append("TOO_MANY_ROWS")
                elif nu == "DUP_VAL_ON_INDEX":
                    results.append("UNIQUE_VIOLATION")
                else:
                    results.append(nu)
            elif target_dialect == Dialect.ORACLE:
                results.append(nu)
            else:
                results.append("SQLEXCEPTION")
        return results

    def _normalize_expr(self, expr: str | None, target_dialect: Dialect, is_trigger: bool = False) -> str:
        if not expr:
            return ""
        s = expr
        if target_dialect == Dialect.POSTGRES:
            if is_trigger:
                s = re.sub(r":([Nn][Ee][Ww])\.", r"\1.", s)
                s = re.sub(r":([Oo][Ll][Dd])\.", r"\1.", s)
            s = re.sub(r"\b[A-Za-z0-9_]+%NOTFOUND\b", "NOT FOUND", s, flags=re.IGNORECASE)
            s = re.sub(r"\b[A-Za-z0-9_]+%FOUND\b", "FOUND", s, flags=re.IGNORECASE)
            s = re.sub(r"\b[A-Za-z0-9_]+%ISOPEN\b", "IS OPEN", s, flags=re.IGNORECASE)
            s = re.sub(r"\bNVL\(", "COALESCE(", s, flags=re.IGNORECASE)
            s = re.sub(r"\bSYSDATE\b", "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)
            s = re.sub(r"\bSYSTIMESTAMP\b", "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)
        elif target_dialect == Dialect.MYSQL:
            if is_trigger:
                s = re.sub(r":([Nn][Ee][Ww])\.", r"\1.", s)
                s = re.sub(r":([Oo][Ll][Dd])\.", r"\1.", s)
            s = re.sub(r"\b[A-Za-z0-9_]+%NOTFOUND\b", "v_not_found = 1", s, flags=re.IGNORECASE)
            s = re.sub(r"\b[A-Za-z0-9_]+%FOUND\b", "v_not_found = 0", s, flags=re.IGNORECASE)
            s = re.sub(r"\bNVL\(", "IFNULL(", s, flags=re.IGNORECASE)
            s = re.sub(r"\bSYSDATE\b", "NOW()", s, flags=re.IGNORECASE)
            s = re.sub(r"\bSYSTIMESTAMP\b", "NOW()", s, flags=re.IGNORECASE)
        elif target_dialect == Dialect.TSQL:
            if is_trigger:
                s = re.sub(r":([Nn][Ee][Ww])\.", r"inserted.", s)
                s = re.sub(r":([Oo][Ll][Dd])\.", r"deleted.", s)
            s = re.sub(r"\b[A-Za-z0-9_]+%NOTFOUND\b", "@@FETCH_STATUS <> 0", s, flags=re.IGNORECASE)
            s = re.sub(r"\b[A-Za-z0-9_]+%FOUND\b", "@@FETCH_STATUS = 0", s, flags=re.IGNORECASE)
            s = re.sub(r"\bNVL\(", "ISNULL(", s, flags=re.IGNORECASE)
            s = re.sub(r"\bSYSDATE\b", "GETDATE()", s, flags=re.IGNORECASE)
            s = re.sub(r"\bSYSTIMESTAMP\b", "SYSDATETIME()", s, flags=re.IGNORECASE)
        elif target_dialect == Dialect.ORACLE:
            if is_trigger:
                s = re.sub(r"(?<!:)\b(NEW|OLD)\.", r":\1.", s)
        return s

    def _normalize_pseudo_record(self, target: str, dialect: Dialect) -> str:
        if dialect == Dialect.ORACLE:
            if not target.startswith(":"):
                return ":" + target
            return target
        return target.lstrip(":")
