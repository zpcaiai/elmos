"""Control Flow Graph (CFG) and Dominator Tree Analysis.

Builds BasicBlocks and directed control flow edges from Universal AST statements,
and calculates dominance, immediate dominators, dominance frontiers, and natural loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import (
    BreakStmt,
    ContinueStmt,
    ForEachStmt,
    ForLoopStmt,
    IfElseStmt,
    ReturnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UniversalExpr,
    UniversalMethod,
    UniversalStmt,
    WhileStmt,
)


class CfgEdgeKind(str, Enum):
    FALLTHROUGH = "fallthrough"
    TRUE_BRANCH = "true_branch"
    FALSE_BRANCH = "false_branch"
    LOOP_BACK = "loop_back"
    LOOP_EXIT = "loop_exit"
    EXCEPTION_UNWIND = "exception_unwind"
    RETURN = "return"


@dataclass
class CfgEdge:
    src: int
    dst: int
    kind: CfgEdgeKind
    condition: Optional[UniversalExpr] = None


@dataclass
class BasicBlock:
    block_id: int
    label: str = ""
    stmts: list[UniversalStmt] = field(default_factory=list)
    predecessors: list[int] = field(default_factory=list)
    successors: list[int] = field(default_factory=list)
    is_entry: bool = False
    is_exit: bool = False


class ControlFlowGraph:
    """Directed Control Flow Graph representing method execution flow."""

    def __init__(self) -> None:
        self.blocks: dict[int, BasicBlock] = {}
        self.edges: list[CfgEdge] = []
        self.entry_id: int = 0
        self.exit_id: int = -1

    def add_block(self, label: str = "", is_entry: bool = False, is_exit: bool = False) -> BasicBlock:
        b_id = len(self.blocks)
        blk = BasicBlock(block_id=b_id, label=label or f"BB_{b_id}", is_entry=is_entry, is_exit=is_exit)
        self.blocks[b_id] = blk
        if is_entry:
            self.entry_id = b_id
        if is_exit:
            self.exit_id = b_id
        return blk

    def add_edge(self, src: int, dst: int, kind: CfgEdgeKind, cond: Optional[UniversalExpr] = None) -> None:
        if dst not in self.blocks[src].successors:
            self.blocks[src].successors.append(dst)
        if src not in self.blocks[dst].predecessors:
            self.blocks[dst].predecessors.append(src)
        self.edges.append(CfgEdge(src=src, dst=dst, kind=kind, condition=cond))

    def prune_unreachable_blocks(self) -> None:
        """Removes blocks that cannot be reached from the entry block."""
        visited: set[int] = set()
        queue = [self.entry_id]
        while queue:
            node = queue.pop(0)
            if node not in visited:
                visited.add(node)
                if node in self.blocks:
                    for succ in self.blocks[node].successors:
                        if succ not in visited:
                            queue.append(succ)

        unreachable = set(self.blocks.keys()) - visited
        for u in unreachable:
            self.edges = [e for e in self.edges if e.src != u and e.dst != u]
            if u in self.blocks:
                del self.blocks[u]
        for blk in self.blocks.values():
            blk.predecessors = [p for p in blk.predecessors if p in self.blocks]
            blk.successors = [s for s in blk.successors if s in self.blocks]

    def compute_dominance(self) -> dict[int, set[int]]:
        """Calculates dominator set Dom(n) for each block n using iterative forward dataflow."""
        all_blocks = set(self.blocks.keys())
        dom: dict[int, set[int]] = {b: set(all_blocks) for b in all_blocks}
        dom[self.entry_id] = {self.entry_id}

        changed = True
        while changed:
            changed = False
            for b_id in all_blocks:
                if b_id == self.entry_id:
                    continue
                preds = self.blocks[b_id].predecessors
                if not preds:
                    new_dom = {b_id}
                else:
                    pred_intersection = set.intersection(*(dom[p] for p in preds))
                    new_dom = {b_id} | pred_intersection

                if new_dom != dom[b_id]:
                    dom[b_id] = new_dom
                    changed = True

        return dom

    def compute_immediate_dominators(self) -> dict[int, int]:
        """Calculates immediate dominator idom(n) for each block n."""
        dom = self.compute_dominance()
        idom: dict[int, int] = {}
        all_blocks = set(self.blocks.keys())

        for b_id in all_blocks:
            if b_id == self.entry_id:
                continue
            strict_doms = dom[b_id] - {b_id}
            # idom(b_id) is the unique d in strict_doms that does not strictly dominate any other element of strict_doms
            for d in strict_doms:
                if (dom[d] - {d}) == (strict_doms - {d}):
                    idom[b_id] = d
                    break
            if b_id not in idom and strict_doms:
                # Max-depth dominator heuristic
                idom[b_id] = max(strict_doms, key=lambda x: len(dom[x]))

        return idom

    def compute_dominance_frontier(self) -> dict[int, set[int]]:
        """Calculates dominance frontiers DF(n) for SSA phi-placement."""
        dom = self.compute_dominance()
        df: dict[int, set[int]] = {b: set() for b in self.blocks}

        for x in self.blocks:
            for y in self.blocks[x].successors:
                # If x does not strictly dominate y, y is in DF(x)
                if x not in (dom[y] - {y}):
                    df[x].add(y)

        # Bottom-up propagation
        idom = self.compute_immediate_dominators()
        tree_children: dict[int, list[int]] = {b: [] for b in self.blocks}
        for b, parent in idom.items():
            tree_children[parent].append(b)

        def propagate_df(node: int) -> None:
            for child in tree_children[node]:
                propagate_df(child)
                for w in df[child]:
                    if node not in (dom[w] - {w}):
                        df[node].add(w)

        propagate_df(self.entry_id)
        return df

    def find_natural_loops(self) -> list[dict[str, Any]]:
        """Identifies back-edges (n -> h where h dominates n) and natural loop bodies."""
        dom = self.compute_dominance()
        loops: list[dict[str, Any]] = []

        for edge in self.edges:
            n = edge.src
            h = edge.dst
            if h in dom[n]:  # Back-edge found: h dominates n
                # Loop body consists of all nodes that can reach n without going through h
                body: set[int] = {h, n}
                stack = [n]
                while stack:
                    curr = stack.pop()
                    for p in self.blocks[curr].predecessors:
                        if p not in body:
                            body.add(p)
                            stack.append(p)
                loops.append({
                    "header": h,
                    "latch": n,
                    "body": sorted(list(body)),
                    "back_edge": edge
                })
        return loops


class CfgBuilder:
    """Constructs a ControlFlowGraph from AST statements."""

    @classmethod
    def build_from_method(cls, method: UniversalMethod) -> ControlFlowGraph:
        cfg = ControlFlowGraph()
        entry = cfg.add_block(label="entry", is_entry=True)
        exit_block = cfg.add_block(label="exit", is_exit=True)

        current_block = entry
        current_block = cls._build_stmt_list(cfg, method.body, current_block, exit_block.block_id, break_dst=None, cont_dst=None)
        if current_block.block_id != exit_block.block_id and (current_block.stmts or current_block.predecessors):
            cfg.add_edge(current_block.block_id, exit_block.block_id, CfgEdgeKind.RETURN)

        cfg.prune_unreachable_blocks()
        return cfg

    @classmethod
    def _build_stmt_list(
        cls,
        cfg: ControlFlowGraph,
        stmts: list[UniversalStmt],
        current: BasicBlock,
        exit_id: int,
        break_dst: Optional[int],
        cont_dst: Optional[int]
    ) -> BasicBlock:
        curr = current
        for stmt in stmts:
            if isinstance(stmt, ReturnStmt):
                curr.stmts.append(stmt)
                cfg.add_edge(curr.block_id, exit_id, CfgEdgeKind.RETURN)
                curr = cfg.add_block(label="unreachable_after_return")

            elif isinstance(stmt, ThrowStmt):
                curr.stmts.append(stmt)
                cfg.add_edge(curr.block_id, exit_id, CfgEdgeKind.EXCEPTION_UNWIND)
                curr = cfg.add_block(label="unreachable_after_throw")

            elif isinstance(stmt, BreakStmt):
                curr.stmts.append(stmt)
                if break_dst is not None:
                    cfg.add_edge(curr.block_id, break_dst, CfgEdgeKind.LOOP_EXIT)
                curr = cfg.add_block(label="unreachable_after_break")

            elif isinstance(stmt, ContinueStmt):
                curr.stmts.append(stmt)
                if cont_dst is not None:
                    cfg.add_edge(curr.block_id, cont_dst, CfgEdgeKind.LOOP_BACK)
                curr = cfg.add_block(label="unreachable_after_continue")

            elif isinstance(stmt, IfElseStmt):
                then_block = cfg.add_block(label="if_then")
                else_block = cfg.add_block(label="if_else") if stmt.else_body else None
                join_block = cfg.add_block(label="if_join")

                cfg.add_edge(curr.block_id, then_block.block_id, CfgEdgeKind.TRUE_BRANCH, stmt.condition)
                if else_block:
                    cfg.add_edge(curr.block_id, else_block.block_id, CfgEdgeKind.FALSE_BRANCH, stmt.condition)
                else:
                    cfg.add_edge(curr.block_id, join_block.block_id, CfgEdgeKind.FALSE_BRANCH, stmt.condition)

                then_end = cls._build_stmt_list(cfg, stmt.then_body, then_block, exit_id, break_dst, cont_dst)
                if then_end.successors == [] or then_end.block_id != exit_id:
                    cfg.add_edge(then_end.block_id, join_block.block_id, CfgEdgeKind.FALLTHROUGH)

                if else_block:
                    else_end = cls._build_stmt_list(cfg, stmt.else_body, else_block, exit_id, break_dst, cont_dst)
                    if else_end.successors == [] or else_end.block_id != exit_id:
                        cfg.add_edge(else_end.block_id, join_block.block_id, CfgEdgeKind.FALLTHROUGH)

                curr = join_block

            elif isinstance(stmt, WhileStmt):
                header_block = cfg.add_block(label="while_header")
                body_block = cfg.add_block(label="while_body")
                after_block = cfg.add_block(label="while_after")

                cfg.add_edge(curr.block_id, header_block.block_id, CfgEdgeKind.FALLTHROUGH)
                cfg.add_edge(header_block.block_id, body_block.block_id, CfgEdgeKind.TRUE_BRANCH, stmt.condition)
                cfg.add_edge(header_block.block_id, after_block.block_id, CfgEdgeKind.LOOP_EXIT, stmt.condition)

                body_end = cls._build_stmt_list(cfg, stmt.body, body_block, exit_id, break_dst=after_block.block_id, cont_dst=header_block.block_id)
                cfg.add_edge(body_end.block_id, header_block.block_id, CfgEdgeKind.LOOP_BACK)

                curr = after_block

            elif isinstance(stmt, TryCatchFinallyStmt):
                try_block = cfg.add_block(label="try_block")
                finally_block = cfg.add_block(label="finally_block") if stmt.finally_body else None
                join_block = cfg.add_block(label="try_join")

                cfg.add_edge(curr.block_id, try_block.block_id, CfgEdgeKind.FALLTHROUGH)
                try_end = cls._build_stmt_list(cfg, stmt.try_body, try_block, exit_id, break_dst, cont_dst)

                target_after_try = finally_block.block_id if finally_block else join_block.block_id
                cfg.add_edge(try_end.block_id, target_after_try, CfgEdgeKind.FALLTHROUGH)

                for catch in stmt.catch_clauses:
                    catch_block = cfg.add_block(label=f"catch_{catch.exception_type}")
                    cfg.add_edge(try_block.block_id, catch_block.block_id, CfgEdgeKind.EXCEPTION_UNWIND)
                    catch_end = cls._build_stmt_list(cfg, catch.body, catch_block, exit_id, break_dst, cont_dst)
                    cfg.add_edge(catch_end.block_id, target_after_try, CfgEdgeKind.FALLTHROUGH)

                if finally_block:
                    finally_end = cls._build_stmt_list(cfg, stmt.finally_body, finally_block, exit_id, break_dst, cont_dst)
                    cfg.add_edge(finally_end.block_id, join_block.block_id, CfgEdgeKind.FALLTHROUGH)

                curr = join_block

            else:
                curr.stmts.append(stmt)

        return curr
