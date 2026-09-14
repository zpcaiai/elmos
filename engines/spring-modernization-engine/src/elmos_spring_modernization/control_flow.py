from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .java_ast import MethodDeclaration, TypeDeclaration, CompilationUnit


@dataclass
class BasicBlock:
    id: int
    kind: str = "NORMAL"  # ENTRY, EXIT, NORMAL, BRANCH, LOOP, TRY, CATCH, FINALLY
    statements: List[str] = field(default_factory=list)
    predecessors: List["BasicBlock"] = field(default_factory=list, repr=False)
    successors: List["BasicBlock"] = field(default_factory=list, repr=False)

    def add_statement(self, stmt: str) -> None:
        cleaned = stmt.strip()
        if cleaned:
            self.statements.append(cleaned)


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


class ControlFlowGraphBuilder:
    """
    Builds method-level Control Flow Graphs (CFG) decomposing statement sequences
    into basic blocks with conditional, loop, and exception edges.
    """

    @classmethod
    def build_cfg(cls, method: MethodDeclaration) -> ControlFlowGraph:
        if not method.body:
            entry = BasicBlock(id=0, kind="ENTRY")
            exit_blk = BasicBlock(id=1, kind="EXIT")
            entry.successors.append(exit_blk)
            exit_blk.predecessors.append(entry)
            return ControlFlowGraph(method.name, entry, exit_blk, [entry, exit_blk])

        raw = method.body.strip()
        if raw.startswith("{") and raw.endswith("}"):
            inner = raw[1:-1].strip()
        else:
            inner = raw

        blocks: List[BasicBlock] = []
        entry = BasicBlock(id=0, kind="ENTRY")
        exit_blk = BasicBlock(id=999, kind="EXIT")
        blocks.append(entry)

        current_block = BasicBlock(id=len(blocks), kind="NORMAL")
        entry.successors.append(current_block)
        current_block.predecessors.append(entry)
        blocks.append(current_block)

        lines = [line.strip() for line in inner.splitlines() if line.strip()]

        for raw_line in lines:
            line = raw_line.lstrip("}").strip()
            if not line:
                continue

            # Control flow keywords detection
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
                # Loop back edge
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
                # Next statements go into a new block
                current_block = BasicBlock(id=len(blocks), kind="NORMAL")
                blocks.append(current_block)

            else:
                current_block.add_statement(raw_line)

        if exit_blk not in current_block.successors and current_block.statements:
            current_block.successors.append(exit_blk)
            exit_blk.predecessors.append(current_block)

        blocks.append(exit_blk)
        return ControlFlowGraph(method.name, entry, exit_blk, blocks)


# ==============================================================================
# Spring & Enterprise Vulnerability Detectors (Gap 3 Core Applications)
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
    Detects internal self-invocations of @Transactional methods within the same class.
    In Spring AOP proxy architecture, calls via 'this.someMethod()' or unqualified
    'someMethod()' bypass the Spring Proxy, causing silent loss of transaction boundaries!
    """

    @classmethod
    def analyze_type(cls, type_decl: TypeDeclaration) -> List[Finding]:
        findings: List[Finding] = []

        # 1. Identify all @Transactional methods in the class
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

        # 2. Inspect every caller method's CFG statements for self-calls
        for caller in methods:
            cfg = ControlFlowGraphBuilder.build_cfg(caller)
            for stmt in cfg.get_all_statements():
                for target_tx in tx_methods:
                    if caller.name == target_tx:
                        # Recursive calls or other statements
                        continue

                    # Matches 'this.target(' or bare 'target(' (not prefixed by otherObject.)
                    pattern = rf"(?:this\s*\.\s*{re.escape(target_tx)}\s*\(|(?<![\w.]){re.escape(target_tx)}\s*\()"
                    if re.search(pattern, stmt):
                        findings.append(Finding(
                            rule_id="SPRING_TX_SELF_INVOCATION",
                            severity="CRITICAL",
                            message=(
                                f"Method '{caller.name}' self-invokes @Transactional method '{target_tx}' "
                                f"directly in class '{type_decl.name}'. This bypasses Spring AOP proxy and "
                                f"silently strips transactionality!"
                            ),
                            location=f"{type_decl.name}.{caller.name}() -> {target_tx}()",
                            remediation=(
                                f"Refactor '{target_tx}()' into a separate @Service component or use "
                                f"self-injected proxy bean: @Autowired private {type_decl.name} self; self.{target_tx}();"
                            )
                        ))

        return findings


class SecurityContextTaintAnalyzer:
    """
    Analyzes SecurityContextHolder manipulation across method control flow.
    Flags instances where setAuthentication() is called without a guaranteed
    clearContext() in a finally block, causing critical thread-pool context leaks.
    """

    @classmethod
    def analyze_method(cls, method: MethodDeclaration, class_name: str = "Unknown") -> List[Finding]:
        findings: List[Finding] = []
        if not method.body:
            return findings

        cfg = ControlFlowGraphBuilder.build_cfg(method)
        has_set_auth = False
        has_clear_context_in_finally = False

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


class HibernateLazyNPlusOneDetector:
    """
    Detects Hibernate/JPA N+1 query anti-patterns by tracing relationship getter calls
    inside loop basic blocks of method CFGs.
    """

    RELATION_GETTER_PATTERN = re.compile(r"\b\w+\.get(?:Items|Orders|Details|Roles|Permissions|Children|Products)\s*\(")

    @classmethod
    def analyze_method(cls, method: MethodDeclaration, class_name: str = "Unknown") -> List[Finding]:
        findings: List[Finding] = []
        if not method.body:
            return findings

        cfg = ControlFlowGraphBuilder.build_cfg(method)
        for block in cfg.blocks:
            if block.kind == "LOOP":
                for stmt in block.statements:
                    match = cls.RELATION_GETTER_PATTERN.search(stmt)
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
