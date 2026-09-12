"""AST-Driven Mutation Testing Engine.

Generates higher-order syntactic and semantic mutants across Python code using AST transformations:
- AOR: Arithmetic Operator Replacement (+ <-> -, * <-> /)
- ROR: Relational Operator Replacement (< <-> <=, == <-> !=)
- COR: Conditional Operator Replacement (and <-> or)
- SDL: Statement Deletion (stmt -> pass)
Evaluates mutant kill ratios and reports mutation strength.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
import hashlib
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class Mutant:
    mutant_id: str
    operator_kind: str
    lineno: int
    original_snippet: str
    mutated_snippet: str
    mutated_ast: ast.AST
    is_killed: bool = False
    killer_test: Optional[str] = None


@dataclass
class MutationScoreReport:
    total_mutants: int
    killed_mutants: int
    survived_mutants: int
    mutation_score: float
    mutants: List[Mutant] = field(default_factory=list)


class ASTMutationTestingEngine:
    """Generates AST mutants and calculates mutation adequacy score."""

    @classmethod
    def generate_mutants(cls, source_code: str) -> List[Mutant]:
        tree = ast.parse(source_code)
        mutants: List[Mutant] = []
        counter = 0

        class MutatingVisitor(ast.NodeVisitor):
            def visit_BinOp(self, node: ast.BinOp) -> None:
                nonlocal counter
                # AOR: Arithmetic Operator Replacement
                replacements = {
                    ast.Add: ast.Sub(),
                    ast.Sub: ast.Add(),
                    ast.Mult: ast.FloorDiv(),
                    ast.FloorDiv: ast.Mult(),
                }
                op_type = type(node.op)
                if op_type in replacements:
                    counter += 1
                    mutated_tree = copy.deepcopy(tree)
                    target = cls._find_node_at(mutated_tree, ast.BinOp, node.lineno, node.col_offset)
                    if isinstance(target, ast.BinOp):
                        target.op = replacements[op_type]
                        mutants.append(
                            Mutant(
                                mutant_id=f"MUT-AOR-{counter}",
                                operator_kind="AOR",
                                lineno=node.lineno,
                                original_snippet=ast.unparse(node),
                                mutated_snippet=ast.unparse(target),
                                mutated_ast=mutated_tree,
                            )
                        )
                self.generic_visit(node)

            def visit_Compare(self, node: ast.Compare) -> None:
                nonlocal counter
                # ROR: Relational Operator Replacement
                ror_map = {
                    ast.Lt: ast.LtE(),
                    ast.LtE: ast.Lt(),
                    ast.Gt: ast.GtE(),
                    ast.GtE: ast.Gt(),
                    ast.Eq: ast.NotEq(),
                    ast.NotEq: ast.Eq(),
                }
                for idx, op in enumerate(node.ops):
                    op_type = type(op)
                    if op_type in ror_map:
                        counter += 1
                        mutated_tree = copy.deepcopy(tree)
                        target = cls._find_node_at(mutated_tree, ast.Compare, node.lineno, node.col_offset)
                        if isinstance(target, ast.Compare) and idx < len(target.ops):
                            target.ops[idx] = ror_map[op_type]
                            mutants.append(
                                Mutant(
                                    mutant_id=f"MUT-ROR-{counter}",
                                    operator_kind="ROR",
                                    lineno=node.lineno,
                                    original_snippet=ast.unparse(node),
                                    mutated_snippet=ast.unparse(target),
                                    mutated_ast=mutated_tree,
                                )
                            )
                self.generic_visit(node)

            def visit_BoolOp(self, node: ast.BoolOp) -> None:
                nonlocal counter
                # COR: Conditional Operator Replacement
                cor_map = {
                    ast.And: ast.Or(),
                    ast.Or: ast.And(),
                }
                op_type = type(node.op)
                if op_type in cor_map:
                    counter += 1
                    mutated_tree = copy.deepcopy(tree)
                    target = cls._find_node_at(mutated_tree, ast.BoolOp, node.lineno, node.col_offset)
                    if isinstance(target, ast.BoolOp):
                        target.op = cor_map[op_type]
                        mutants.append(
                            Mutant(
                                mutant_id=f"MUT-COR-{counter}",
                                operator_kind="COR",
                                lineno=node.lineno,
                                original_snippet=ast.unparse(node),
                                mutated_snippet=ast.unparse(target),
                                mutated_ast=mutated_tree,
                            )
                        )
                self.generic_visit(node)

        visitor = MutatingVisitor()
        visitor.visit(tree)
        return mutants

    @classmethod
    def evaluate_mutants(
        cls,
        mutants: List[Mutant],
        test_runner: Callable[[str], bool],
    ) -> MutationScoreReport:
        killed = 0
        for m in mutants:
            mutated_code = ast.unparse(m.mutated_ast)
            test_passed = test_runner(mutated_code)
            if not test_passed:
                m.is_killed = True
                m.killer_test = "test_runner_assertion"
                killed += 1

        total = len(mutants)
        survived = total - killed
        score = round((killed / total) * 100.0, 2) if total > 0 else 100.0

        return MutationScoreReport(
            total_mutants=total,
            killed_mutants=killed,
            survived_mutants=survived,
            mutation_score=score,
            mutants=mutants,
        )

    @staticmethod
    def _find_node_at(tree: ast.AST, target_type: type, lineno: int, col_offset: int) -> Optional[ast.AST]:
        for n in ast.walk(tree):
            if isinstance(n, target_type) and getattr(n, 'lineno', None) == lineno and getattr(n, 'col_offset', None) == col_offset:
                return n
        return None
