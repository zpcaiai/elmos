from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .java_ast import (
    JavaASTNode,
    CompilationUnit,
    TypeDeclaration,
    MethodDeclaration,
    Statement,
    Expression,
    Block,
    ExpressionStatement,
    VariableDeclarationStatement,
    IfStatement,
    WhileStatement,
    ForStatement,
    CatchClause,
    TryCatchFinallyStatement,
    ReturnStatement,
    MethodInvocation,
    IdentifierExpression,
    LiteralExpression,
    FieldAccessExpression,
)


@dataclass
class BasicBlock:
    id: int
    kind: str = "NORMAL"  # ENTRY, EXIT, NORMAL, BRANCH, LOOP, TRY, CATCH, FINALLY
    statements: List[str] = field(default_factory=list)
    ast_nodes: List[Statement] = field(default_factory=list)
    predecessors: List["BasicBlock"] = field(default_factory=list, repr=False)
    successors: List["BasicBlock"] = field(default_factory=list, repr=False)

    def add_statement(self, stmt_repr: str, node: Optional[Statement] = None) -> None:
        cleaned = stmt_repr.strip()
        if cleaned:
            self.statements.append(cleaned)
        if node:
            self.ast_nodes.append(node)


@dataclass
class ControlFlowGraph:
    method_name: str
    entry_block: BasicBlock
    exit_block: BasicBlock
    blocks: List[BasicBlock] = field(default_factory=list)

    def get_all_statements(self) -> List[str]:
        stmts = []
        for b in self.blocks:
            stmts.extend(b.statements)
        return stmts


def extract_all_invocations(node: Optional[JavaASTNode]) -> List[MethodInvocation]:
    """
    Recursively traverses an AST statement or expression tree and extracts all
    strongly typed MethodInvocation AST nodes.
    """
    if node is None:
        return []

    invocations: List[MethodInvocation] = []

    if isinstance(node, MethodInvocation):
        invocations.append(node)
        if node.select:
            invocations.extend(extract_all_invocations(node.select))
        for arg in node.arguments:
            invocations.extend(extract_all_invocations(arg))
        return invocations

    if isinstance(node, Block):
        for s in node.statements:
            invocations.extend(extract_all_invocations(s))
    elif isinstance(node, ExpressionStatement):
        invocations.extend(extract_all_invocations(node.expression))
    elif isinstance(node, VariableDeclarationStatement):
        if node.initializer:
            invocations.extend(extract_all_invocations(node.initializer))
    elif isinstance(node, IfStatement):
        invocations.extend(extract_all_invocations(node.condition))
        invocations.extend(extract_all_invocations(node.then_branch))
        if node.else_branch:
            invocations.extend(extract_all_invocations(node.else_branch))
    elif isinstance(node, (WhileStatement, ForStatement)):
        invocations.extend(extract_all_invocations(node.body))
    elif isinstance(node, TryCatchFinallyStatement):
        invocations.extend(extract_all_invocations(node.try_block))
        for c in node.catch_clauses:
            invocations.extend(extract_all_invocations(c.body))
        if node.finally_block:
            invocations.extend(extract_all_invocations(node.finally_block))
    elif isinstance(node, ReturnStatement):
        if node.expression:
            invocations.extend(extract_all_invocations(node.expression))
    elif isinstance(node, FieldAccessExpression):
        invocations.extend(extract_all_invocations(node.target))

    return invocations


class ControlFlowGraphBuilder:
    """
    Builds method-level Control Flow Graphs (CFG) from strongly typed Statement AST nodes,
    decomposing execution paths into basic blocks with conditional, loop, and exception edges.
    """

    @classmethod
    def build_cfg(cls, method: MethodDeclaration) -> ControlFlowGraph:
        entry = BasicBlock(id=0, kind="ENTRY")
        exit_blk = BasicBlock(id=999, kind="EXIT")

        if not method.statements and not method.body:
            entry.successors.append(exit_blk)
            exit_blk.predecessors.append(entry)
            return ControlFlowGraph(method.name, entry, exit_blk, [entry, exit_blk])

        blocks: List[BasicBlock] = [entry]
        current_block = BasicBlock(id=len(blocks), kind="NORMAL")
        entry.successors.append(current_block)
        current_block.predecessors.append(entry)
        blocks.append(current_block)

        # 1. Prefer AST-driven CFG construction if statements are parsed
        if method.statements:
            for stmt in method.statements:
                current_block = cls._process_statement_cfg(stmt, current_block, exit_blk, blocks)
        else:
            # Fallback line-by-line parsing if AST statement parsing was bypassed
            current_block = cls._process_raw_lines_fallback(method.body or "", current_block, exit_blk, blocks)

        if exit_blk not in current_block.successors and (current_block.statements or current_block.ast_nodes):
            current_block.successors.append(exit_blk)
            exit_blk.predecessors.append(current_block)

        blocks.append(exit_blk)
        return ControlFlowGraph(method.name, entry, exit_blk, blocks)

    @classmethod
    def _process_statement_cfg(
        cls,
        stmt: Statement,
        current_block: BasicBlock,
        exit_blk: BasicBlock,
        blocks: List[BasicBlock]
    ) -> BasicBlock:
        if isinstance(stmt, IfStatement):
            branch_blk = BasicBlock(id=len(blocks), kind="BRANCH")
            branch_blk.add_statement("if (...) [AST]", stmt)
            current_block.successors.append(branch_blk)
            branch_blk.predecessors.append(current_block)
            blocks.append(branch_blk)
            return branch_blk

        elif isinstance(stmt, (WhileStatement, ForStatement)):
            loop_blk = BasicBlock(id=len(blocks), kind="LOOP")
            loop_blk.add_statement("loop (...) [AST]", stmt)
            current_block.successors.append(loop_blk)
            loop_blk.predecessors.append(current_block)
            loop_blk.successors.append(loop_blk)  # Loop back-edge
            blocks.append(loop_blk)
            return loop_blk

        elif isinstance(stmt, TryCatchFinallyStatement):
            try_blk = BasicBlock(id=len(blocks), kind="TRY")
            try_blk.add_statement("try [AST]", stmt.try_block)
            current_block.successors.append(try_blk)
            try_blk.predecessors.append(current_block)
            blocks.append(try_blk)

            last_flow_blocks = [try_blk]
            for catch_c in stmt.catch_clauses:
                catch_blk = BasicBlock(id=len(blocks), kind="CATCH")
                catch_blk.add_statement(f"catch ({catch_c.param_type} {catch_c.param_name}) [AST]", catch_c.body)
                try_blk.successors.append(catch_blk)
                catch_blk.predecessors.append(try_blk)
                blocks.append(catch_blk)
                last_flow_blocks.append(catch_blk)

            if stmt.finally_block:
                fin_blk = BasicBlock(id=len(blocks), kind="FINALLY")
                fin_blk.add_statement("finally [AST]", stmt.finally_block)
                for blk in last_flow_blocks:
                    blk.successors.append(fin_blk)
                    fin_blk.predecessors.append(blk)
                blocks.append(fin_blk)
                return fin_blk

            join_blk = BasicBlock(id=len(blocks), kind="NORMAL")
            for blk in last_flow_blocks:
                blk.successors.append(join_blk)
                join_blk.predecessors.append(blk)
            blocks.append(join_blk)
            return join_blk

        elif isinstance(stmt, ReturnStatement):
            current_block.add_statement("return [AST]", stmt)
            current_block.successors.append(exit_blk)
            exit_blk.predecessors.append(current_block)
            new_block = BasicBlock(id=len(blocks), kind="NORMAL")
            blocks.append(new_block)
            return new_block

        else:
            current_block.add_statement(stmt.__class__.__name__, stmt)
            return current_block

    @classmethod
    def _process_raw_lines_fallback(
        cls,
        raw_body: str,
        current_block: BasicBlock,
        exit_blk: BasicBlock,
        blocks: List[BasicBlock]
    ) -> BasicBlock:
        raw = raw_body.strip()
        if raw.startswith("{") and raw.endswith("}"):
            inner = raw[1:-1].strip()
        else:
            inner = raw

        lines = [line.strip() for line in inner.splitlines() if line.strip()]
        for raw_line in lines:
            line = raw_line.lstrip("}").strip()
            if not line:
                continue

            if line.startswith("if ") or line.startswith("if(") or line.startswith("else if"):
                branch_blk = BasicBlock(id=len(blocks), kind="BRANCH")
                branch_blk.add_statement(raw_line)
                current_block.successors.append(branch_blk)
                branch_blk.predecessors.append(current_block)
                blocks.append(branch_blk)
                current_block = branch_blk
            elif line.startswith("for ") or line.startswith("for(") or line.startswith("while ") or line.startswith("while("):
                loop_blk = BasicBlock(id=len(blocks), kind="LOOP")
                loop_blk.add_statement(raw_line)
                current_block.successors.append(loop_blk)
                loop_blk.predecessors.append(current_block)
                loop_blk.successors.append(loop_blk)
                blocks.append(loop_blk)
                current_block = loop_blk
            elif line.startswith("try ") or line.startswith("try{") or line.startswith("try ("):
                try_blk = BasicBlock(id=len(blocks), kind="TRY")
                try_blk.add_statement(raw_line)
                current_block.successors.append(try_blk)
                try_blk.predecessors.append(current_block)
                blocks.append(try_blk)
                current_block = try_blk
            elif line.startswith("catch ") or line.startswith("catch(") or line.startswith("catch (") or line.startswith("catch{"):
                catch_blk = BasicBlock(id=len(blocks), kind="CATCH")
                catch_blk.add_statement(raw_line)
                current_block.successors.append(catch_blk)
                catch_blk.predecessors.append(current_block)
                blocks.append(catch_blk)
                current_block = catch_blk
            elif line.startswith("finally ") or line.startswith("finally{") or line.startswith("finally"):
                fin_blk = BasicBlock(id=len(blocks), kind="FINALLY")
                fin_blk.add_statement(raw_line)
                current_block.successors.append(fin_blk)
                fin_blk.predecessors.append(current_block)
                blocks.append(fin_blk)
                current_block = fin_blk
            elif line.startswith("return ") or line.startswith("return;") or line.startswith("throw "):
                current_block.add_statement(raw_line)
                current_block.successors.append(exit_blk)
                exit_blk.predecessors.append(current_block)
                current_block = BasicBlock(id=len(blocks), kind="NORMAL")
                blocks.append(current_block)
            else:
                current_block.add_statement(raw_line)

        return current_block


# ==============================================================================
# Spring & Enterprise Vulnerability Detectors (Compiler-grade AST Analysis)
# ==============================================================================

@dataclass
class Finding:
    rule_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    message: str
    location: str
    remediation: str


class TransactionalSelfInvocationDetector:
    """
    Compiler-grade AST detector for internal self-invocations of @Transactional methods.
    Analyzes MethodInvocation AST nodes to verify receiver expression:
    - select is None (implicit this.method()) -> PROXY BYPASS (CRITICAL)
    - select is this (explicit this.method()) -> PROXY BYPASS (CRITICAL)
    - select is otherService -> VALID PROXY CALL (ZERO FALSE POSITIVES)
    - identifier in local variable -> SKIPPED (ZERO FALSE POSITIVES)
    """

    @classmethod
    def analyze_type(cls, type_decl: TypeDeclaration) -> List[Finding]:
        findings: List[Finding] = []

        # 1. Identify all @Transactional methods declared in the class
        tx_methods: Set[str] = set()
        methods: List[MethodDeclaration] = []

        for m in type_decl.members:
            if isinstance(m, MethodDeclaration):
                methods.append(m)
                for anno in m.annotations:
                    if anno.name == "Transactional" or (anno.resolved_type and anno.resolved_type.endswith(".Transactional")):
                        tx_methods.add(m.name)

        if not tx_methods:
            return findings

        # 2. Inspect every caller method's AST statements for self-invocations
        for caller in methods:
            invocations = extract_all_invocations(caller.body_block)

            # Fallback to line regex if statement parsing had no nodes
            if not invocations and caller.body:
                cfg = ControlFlowGraphBuilder.build_cfg(caller)
                for stmt in cfg.get_all_statements():
                    for target_tx in tx_methods:
                        if caller.name == target_tx:
                            continue
                        pattern = rf"(?:this\s*\.\s*{re.escape(target_tx)}\s*\(|(?<![\w.]){re.escape(target_tx)}\s*\()"
                        if re.search(pattern, stmt):
                            findings.append(cls._create_finding(type_decl.name, caller.name, target_tx))
                continue

            for inv in invocations:
                if inv.method_name not in tx_methods:
                    continue
                if caller.name == inv.method_name:
                    continue  # Recursive calls or self

                # Check Receiver:
                # 1) implicit this (inv.select is None)
                # 2) explicit this (inv.select is IdentifierExpression and name == 'this')
                is_self = False
                if inv.select is None:
                    is_self = True
                elif isinstance(inv.select, IdentifierExpression) and inv.select.name == "this":
                    is_self = True

                if is_self:
                    findings.append(cls._create_finding(type_decl.name, caller.name, inv.method_name))

        return findings

    @classmethod
    def analyze_source(cls, source_code: str) -> List[Finding]:
        """
        Compiler-grade analysis prioritizing Java Engine Worker (Route A).
        Falls back to standalone Python AST parser if Java Worker is unavailable.
        """
        from .java_worker_bridge import JavaWorkerClient
        worker = JavaWorkerClient()
        if worker.is_worker_available():
            res = worker.analyze_with_java_worker(source_code, "TRANSACTIONAL_SELF_INVOCATION")
            if res.status == "SUCCESS":
                return [
                    Finding(
                        rule_id=f.rule_id,
                        severity=f.severity,
                        message=f.message,
                        location=f.location,
                        remediation=f.remediation
                    )
                    for f in res.findings
                ]

        # Standalone Python AST fallback
        from .java_ast import JavaASTParser, JavaLexer
        p = JavaASTParser(JavaLexer(source_code).tokenize(), source=source_code).parse()
        findings: List[Finding] = []
        for t in p.type_declarations:
            findings.extend(cls.analyze_type(t))
        return findings

    @classmethod
    def _create_finding(cls, class_name: str, caller_name: str, target_name: str) -> Finding:
        return Finding(
            rule_id="SPRING_TX_SELF_INVOCATION",
            severity="CRITICAL",
            message=(
                f"Method '{caller_name}' self-invokes @Transactional method '{target_name}' "
                f"directly in class '{class_name}'. This bypasses Spring AOP proxy and "
                f"silently strips transactionality!"
            ),
            location=f"{class_name}.{caller_name}() -> {target_name}()",
            remediation=(
                f"Refactor '{target_name}()' into a separate @Service component or use "
                f"self-injected proxy bean: @Autowired private {class_name} self; self.{target_name}();"
            )
        )


class SecurityContextTaintAnalyzer:
    """
    Compiler-grade AST analyzer for SecurityContextHolder manipulation across method control flow.
    Flags instances where setAuthentication() is invoked without a guaranteed
    clearContext() inside a 'finally' block of TryCatchFinallyStatement.
    """

    @classmethod
    def analyze_method(cls, method: MethodDeclaration, class_name: str = "Unknown") -> List[Finding]:
        findings: List[Finding] = []
        if not method.body_block and not method.body:
            return findings

        invocations = extract_all_invocations(method.body_block)
        has_set_auth = False
        has_clear_context_in_finally = False

        if invocations:
            for inv in invocations:
                # Check for setAuthentication call
                if inv.method_name == "setAuthentication":
                    has_set_auth = True

            # Check if enclosed in TryCatchFinallyStatement with clearContext in finally_block
            if method.body_block:
                for stmt in method.body_block.statements:
                    if isinstance(stmt, TryCatchFinallyStatement) and stmt.finally_block:
                        finally_invs = extract_all_invocations(stmt.finally_block)
                        for fin_inv in finally_invs:
                            if fin_inv.method_name == "clearContext":
                                has_clear_context_in_finally = True
        else:
            # Fallback regex
            cfg = ControlFlowGraphBuilder.build_cfg(method)
            for block in cfg.blocks:
                for stmt in block.statements:
                    if "SecurityContextHolder.getContext().setAuthentication(" in stmt or "SecurityContextHolder.setContext(" in stmt:
                        has_set_auth = True
                    if block.kind == "FINALLY" and "SecurityContextHolder.clearContext()" in stmt:
                        has_clear_context_in_finally = True

        if has_set_auth and not has_clear_context_in_finally:
            findings.append(Finding(
                rule_id="SECURITY_CONTEXT_LEAK",
                severity="HIGH",
                message=(
                    f"Method '{class_name}.{method.name}' assigns SecurityContext without a guaranteed "
                    f"SecurityContextHolder.clearContext() in a 'finally' block. In thread-pooled web containers "
                    f"(Tomcat/Undertow), this leaks authenticated credentials across requests!"
                ),
                location=f"{class_name}.{method.name}()",
                remediation="Ensure SecurityContextHolder.clearContext() is invoked inside a 'finally' block."
            ))

        return findings

    @classmethod
    def analyze_source(cls, source_code: str) -> List[Finding]:
        """
        Compiler-grade analysis prioritizing Java Engine Worker (Route A).
        Falls back to standalone Python AST parser if Java Worker is unavailable.
        """
        from .java_worker_bridge import JavaWorkerClient
        worker = JavaWorkerClient()
        if worker.is_worker_available():
            res = worker.analyze_with_java_worker(source_code, "SECURITY")
            if res.status == "SUCCESS":
                return [
                    Finding(
                        rule_id=f.rule_id,
                        severity=f.severity,
                        message=f.message,
                        location=f.location,
                        remediation=f.remediation
                    )
                    for f in res.findings
                ]

        # Standalone Python AST fallback
        from .java_ast import JavaASTParser, JavaLexer
        p = JavaASTParser(JavaLexer(source_code).tokenize(), source=source_code).parse()
        findings: List[Finding] = []
        for t in p.type_declarations:
            for m in getattr(t, "members", []):
                if isinstance(m, MethodDeclaration):
                    findings.extend(cls.analyze_method(m, class_name=t.name))
        return findings


class HibernateLazyNPlusOneDetector:
    """
    Compiler-grade AST detector for Hibernate/JPA N+1 query anti-patterns.
    Identifies relational entity getter calls located inside Loop AST statements (WhileStatement, ForStatement).
    """

    RELATION_NAMES = {
        "Items", "Orders", "Details", "Roles", "Permissions",
        "Children", "Products", "Addresses", "Transactions"
    }

    @classmethod
    def analyze_method(cls, method: MethodDeclaration, class_name: str = "Unknown") -> List[Finding]:
        findings: List[Finding] = []
        if not method.body_block and not method.body:
            return findings

        # Check loop AST statements
        if method.body_block:
            for stmt in method.body_block.statements:
                if isinstance(stmt, (WhileStatement, ForStatement)):
                    loop_invs = extract_all_invocations(stmt.body)
                    for inv in loop_invs:
                        if inv.method_name.startswith("get") and inv.method_name[3:] in cls.RELATION_NAMES:
                            findings.append(Finding(
                                rule_id="HIBERNATE_LAZY_N_PLUS_ONE",
                                severity="HIGH",
                                message=(
                                    f"Method '{class_name}.{method.name}' calls relational getter '{inv.method_name}' "
                                    f"inside a loop basic block. This triggers the classic N+1 database query penalty in Hibernate 6!"
                                ),
                                location=f"{class_name}.{method.name}() [Loop: {stmt.__class__.__name__}]",
                                remediation="Refactor repository query to use 'JOIN FETCH' or EntityGraph, or execute a batch fetch."
                            ))
            if findings:
                return findings

        # Fallback to CFG Loop block matching
        cfg = ControlFlowGraphBuilder.build_cfg(method)
        pattern = re.compile(r"\b\w+\.get(?:Items|Orders|Details|Roles|Permissions|Children|Products)\s*\(")
        for block in cfg.blocks:
            if block.kind == "LOOP":
                for stmt in block.statements:
                    match = pattern.search(stmt)
                    if match:
                        getter_name = match.group(0).strip("(")
                        findings.append(Finding(
                            rule_id="HIBERNATE_LAZY_N_PLUS_ONE",
                            severity="HIGH",
                            message=(
                                f"Method '{class_name}.{method.name}' calls relational getter '{getter_name}' "
                                f"inside a loop basic block. This triggers the classic N+1 database query penalty in Hibernate 6!"
                            ),
                            location=f"{class_name}.{method.name}() [Block #{block.id}: LOOP]",
                            remediation="Refactor repository query to use 'JOIN FETCH' or EntityGraph, or execute a batch fetch."
                        ))

        return findings

    @classmethod
    def analyze_source(cls, source_code: str) -> List[Finding]:
        """
        Compiler-grade analysis prioritizing Java Engine Worker (Route A).
        Falls back to standalone Python AST parser if Java Worker is unavailable.
        """
        from .java_worker_bridge import JavaWorkerClient
        worker = JavaWorkerClient()
        if worker.is_worker_available():
            res = worker.analyze_with_java_worker(source_code, "HIBERNATE_LAZY_N_PLUS_ONE")
            if res.status == "SUCCESS":
                return [
                    Finding(
                        rule_id=f.rule_id,
                        severity=f.severity,
                        message=f.message,
                        location=f.location,
                        remediation=f.remediation
                    )
                    for f in res.findings
                ]

        # Standalone Python AST fallback
        from .java_ast import JavaASTParser, JavaLexer
        p = JavaASTParser(JavaLexer(source_code).tokenize(), source=source_code).parse()
        findings: List[Finding] = []
        for t in p.type_declarations:
            for m in getattr(t, "members", []):
                if isinstance(m, MethodDeclaration):
                    findings.extend(cls.analyze_method(m, class_name=t.name))
        return findings

