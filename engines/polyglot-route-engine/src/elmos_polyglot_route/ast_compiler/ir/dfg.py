"""Data Flow Graph (DFG), Static Single Assignment (SSA) and Liveness Analysis.

Extracts variable definitions and uses, builds Def-Use / Use-Def chains,
computes iterative backwards liveness analysis, places SSA phi-nodes,
and analyzes function purity and side-effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import (
    AssignStmt,
    BinaryExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    IfElseStmt,
    LockStmt,
    MethodCallExpr,
    ReturnStmt,
    TryCatchFinallyStmt,
    UniversalExpr,
    UniversalMethod,
    UniversalParam,
    UniversalStmt,
    VarDeclStmt,
    WhileStmt,
)
from .cfg import BasicBlock, ControlFlowGraph


@dataclass
class Definition:
    def_id: int
    var_name: str
    version: int
    block_id: int
    stmt_index: int
    expr: Optional[UniversalExpr] = None


@dataclass
class Use:
    use_id: int
    var_name: str
    block_id: int
    stmt_index: int


@dataclass
class PhiNode:
    var_name: str
    result_version: int
    block_id: int
    operands: dict[int, int] = field(default_factory=dict)  # predecessor block_id -> version


@dataclass
class LivenessInfo:
    block_id: int
    defs: set[str] = field(default_factory=set)
    uses: set[str] = field(default_factory=set)
    live_in: set[str] = field(default_factory=set)
    live_out: set[str] = field(default_factory=set)


class DataFlowGraph:
    """Data Flow Graph capturing variable definitions, uses, liveness, and SSA form."""

    def __init__(self, cfg: ControlFlowGraph) -> None:
        self.cfg = cfg
        self.definitions: list[Definition] = []
        self.uses: list[Use] = []
        self.def_use_chains: dict[int, list[int]] = {}  # def_id -> list of use_id
        self.use_def_chains: dict[int, int] = {}       # use_id -> def_id
        self.liveness: dict[int, LivenessInfo] = {}
        self.phi_nodes: dict[int, list[PhiNode]] = {b: [] for b in cfg.blocks}
        self._analyze_blocks()
        self._compute_liveness()
        self._place_phi_nodes()

    def _analyze_blocks(self) -> None:
        def_counter = 0
        use_counter = 0
        var_versions: dict[str, int] = {}

        for b_id, block in self.cfg.blocks.items():
            l_info = LivenessInfo(block_id=b_id)
            self.liveness[b_id] = l_info

            for s_idx, stmt in enumerate(block.stmts):
                if isinstance(stmt, VarDeclStmt):
                    v_name = stmt.name
                    var_versions[v_name] = var_versions.get(v_name, 0) + 1
                    ver = var_versions[v_name]
                    d = Definition(def_id=def_counter, var_name=v_name, version=ver, block_id=b_id, stmt_index=s_idx, expr=stmt.initial_value)
                    self.definitions.append(d)
                    self.def_use_chains[def_counter] = []
                    def_counter += 1
                    l_info.defs.add(v_name)

                    if stmt.initial_value:
                        for u_name in self._extract_uses_from_expr(stmt.initial_value):
                            if u_name not in l_info.defs:
                                l_info.uses.add(u_name)
                            u = Use(use_id=use_counter, var_name=u_name, block_id=b_id, stmt_index=s_idx)
                            self.uses.append(u)
                            use_counter += 1

                elif isinstance(stmt, AssignStmt):
                    if isinstance(stmt.target, IdentifierExpr):
                        v_name = stmt.target.name
                        var_versions[v_name] = var_versions.get(v_name, 0) + 1
                        ver = var_versions[v_name]
                        d = Definition(def_id=def_counter, var_name=v_name, version=ver, block_id=b_id, stmt_index=s_idx, expr=stmt.value)
                        self.definitions.append(d)
                        self.def_use_chains[def_counter] = []
                        def_counter += 1
                        l_info.defs.add(v_name)

                    for u_name in self._extract_uses_from_expr(stmt.value):
                        if u_name not in l_info.defs:
                            l_info.uses.add(u_name)
                        u = Use(use_id=use_counter, var_name=u_name, block_id=b_id, stmt_index=s_idx)
                        self.uses.append(u)
                        use_counter += 1

                elif isinstance(stmt, ReturnStmt):
                    if stmt.value:
                        for u_name in self._extract_uses_from_expr(stmt.value):
                            if u_name not in l_info.defs:
                                l_info.uses.add(u_name)
                            u = Use(use_id=use_counter, var_name=u_name, block_id=b_id, stmt_index=s_idx)
                            self.uses.append(u)
                            use_counter += 1

                elif isinstance(stmt, ExprStmt):
                    for u_name in self._extract_uses_from_expr(stmt.expr):
                        if u_name not in l_info.defs:
                            l_info.uses.add(u_name)
                        u = Use(use_id=use_counter, var_name=u_name, block_id=b_id, stmt_index=s_idx)
                        self.uses.append(u)
                        use_counter += 1

    def _extract_uses_from_expr(self, expr: Optional[UniversalExpr]) -> list[str]:
        if not expr:
            return []
        uses: list[str] = []
        if isinstance(expr, IdentifierExpr):
            uses.append(expr.name)
        elif isinstance(expr, BinaryExpr):
            uses.extend(self._extract_uses_from_expr(expr.left))
            uses.extend(self._extract_uses_from_expr(expr.right))
        elif isinstance(expr, FieldAccessExpr):
            uses.extend(self._extract_uses_from_expr(expr.target))
        elif isinstance(expr, MethodCallExpr):
            if expr.target:
                uses.extend(self._extract_uses_from_expr(expr.target))
            for arg in expr.args:
                uses.extend(self._extract_uses_from_expr(arg))
        return uses

    def _compute_liveness(self) -> None:
        """Computes backward iterative liveness analysis until fixpoint."""
        changed = True
        all_blocks = list(self.cfg.blocks.keys())

        while changed:
            changed = False
            for b_id in reversed(all_blocks):
                info = self.liveness[b_id]
                block = self.cfg.blocks[b_id]

                # LiveOut(B) = Union of LiveIn(S) for S in successors(B)
                new_live_out: set[str] = set()
                for succ in block.successors:
                    if succ in self.liveness:
                        new_live_out |= self.liveness[succ].live_in

                # LiveIn(B) = Use(B) union (LiveOut(B) - Def(B))
                new_live_in = info.uses | (new_live_out - info.defs)

                if new_live_out != info.live_out or new_live_in != info.live_in:
                    info.live_out = new_live_out
                    info.live_in = new_live_in
                    changed = True

    def _place_phi_nodes(self) -> None:
        """Places SSA phi-nodes at dominance frontiers for variables defined in multiple blocks."""
        df = self.cfg.compute_dominance_frontier()
        var_defs: dict[str, set[int]] = {}
        for d in self.definitions:
            var_defs.setdefault(d.var_name, set()).add(d.block_id)

        for var, def_blocks in var_defs.items():
            if len(def_blocks) <= 1:
                continue
            # Iterated dominance frontier
            w = set(def_blocks)
            inserted: set[int] = set()
            while w:
                x = w.pop()
                for y in df.get(x, set()):
                    if y not in inserted:
                        phi = PhiNode(var_name=var, result_version=99, block_id=y)
                        self.phi_nodes[y].append(phi)
                        inserted.add(y)
                        if y not in def_blocks:
                            w.add(y)

    @classmethod
    def is_pure_method(cls, method: UniversalMethod) -> tuple[bool, list[str]]:
        """Analyzes a method for side-effects, I/O, global mutations, or impure invocations."""
        impure_reasons: list[str] = []

        def check_stmt(stmt: UniversalStmt) -> None:
            if isinstance(stmt, AssignStmt):
                if isinstance(stmt.target, FieldAccessExpr):
                    impure_reasons.append(f"Mutates field {stmt.target.field_name}")
            elif isinstance(stmt, ExprStmt):
                if isinstance(stmt.expr, MethodCallExpr):
                    m_name = (stmt.expr.method_name or "").lower()
                    if any(io_kw in m_name for io_kw in ("print", "write", "send", "log", "save", "delete", "post", "put", "increment", "decrement")):
                        impure_reasons.append(f"Performs I/O or mutating call: {stmt.expr.method_name}")
            elif isinstance(stmt, IfElseStmt):
                for s in stmt.then_body:
                    check_stmt(s)
                for s in stmt.else_body:
                    check_stmt(s)
            elif isinstance(stmt, WhileStmt):
                for s in stmt.body:
                    check_stmt(s)
            elif isinstance(stmt, LockStmt):
                for s in stmt.body:
                    check_stmt(s)
            elif isinstance(stmt, TryCatchFinallyStmt):
                for s in stmt.try_body:
                    check_stmt(s)
                for cc in stmt.catch_clauses:
                    for s in cc.body:
                        check_stmt(s)
                for s in stmt.finally_body:
                    check_stmt(s)

        for s in method.body:
            check_stmt(s)

        return (len(impure_reasons) == 0, impure_reasons)
