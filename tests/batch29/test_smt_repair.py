"""Unit and Integration Tests for Z3 SMT Constraint-Driven Self-Healing Engine."""

from __future__ import annotations

import pytest

from elmos_polyglot_route.ast_compiler.autonomous import (
    SmtAutonomousRepairEngine,
    SmtBoundsAndOverflowSolver,
    SmtNullabilitySolver,
    SmtOwnershipSolver,
    SmtTypeSolver,
)
from elmos_polyglot_route.ast_compiler.ir import (
    BinaryExpr,
    BinaryOperator,
    CastExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    LiteralExpr,
    ReturnStmt,
    UniversalMethod,
    UniversalParam,
    UniversalType,
)


def test_smt_type_widening_solver():
    """Verify Z3 solves formal type rank lattice widening constraints."""
    t_i32 = UniversalType.primitive("i32")
    t_i64 = UniversalType.int64()

    patch = SmtTypeSolver.solve_widening_cast(t_i32, t_i64)
    assert patch is not None
    assert patch.rule_name == "SMT_NUMERIC_WIDENING"
    assert "i32" in patch.description and "i64" in patch.description
    assert "is_widening=True" in patch.smt_model_summary

    # Identity / narrowing should not produce widening patch
    assert SmtTypeSolver.solve_widening_cast(t_i64, t_i32) is None


def test_smt_overflow_bounds_solver():
    """Verify Z3 BitVec arithmetic detects potential overflow and proves safe ranges."""
    # 32-bit addition with full range can overflow
    has_overflow, patch = SmtBoundsAndOverflowSolver.check_addition_overflow(
        bit_width=32,
        operand_min=-2147483648,
        operand_max=2147483647
    )
    assert has_overflow is True
    assert patch is not None
    assert patch.rule_name == "SMT_CHECKED_ARITHMETIC_OR_WIDENING"
    assert "counterexample" in patch.smt_model_summary

    # 32-bit addition with small bounded operands is formally proved overflow-free
    safe_overflow, safe_patch = SmtBoundsAndOverflowSolver.check_addition_overflow(
        bit_width=32,
        operand_min=0,
        operand_max=1000
    )
    assert safe_overflow is False
    assert safe_patch is None


def test_smt_null_guard_solver():
    """Verify Z3 synthesizes null safety check for unguarded nullable dereferences."""
    patch = SmtNullabilitySolver.solve_null_guard(
        var_name="customer",
        is_nullable=True,
        is_dereferenced=True
    )
    assert patch is not None
    assert patch.rule_name == "SMT_NULL_GUARD_SYNTHESIS"
    assert "customer" in patch.description
    assert "requires guard=True" in patch.smt_model_summary

    # Non-nullable reference has no hazard
    assert SmtNullabilitySolver.solve_null_guard("customer", is_nullable=False, is_dereferenced=True) is None


def test_smt_borrow_hazard_solver():
    """Verify Z3 affine ownership solver detects borrow checker aliasing conflicts."""
    # 2 mutable borrows simultaneously violates Rust ownership
    patch = SmtOwnershipSolver.solve_borrow_hazard(
        var_name="buffer",
        shared_borrows=0,
        mut_borrows=2
    )
    assert patch is not None
    assert patch.rule_name == "SMT_AFFINE_OWNERSHIP_CLONE"
    assert "buffer" in patch.description
    assert "valid_borrow=False" in patch.smt_model_summary

    # 1 mutable borrow and 0 shared borrows is valid
    assert SmtOwnershipSolver.solve_borrow_hazard("buffer", shared_borrows=0, mut_borrows=1) is None

    # Multiple shared borrows with 0 mutable borrows is valid
    assert SmtOwnershipSolver.solve_borrow_hazard("buffer", shared_borrows=5, mut_borrows=0) is None


def test_smt_autonomous_repair_pipeline():
    """Verify end-to-end AST inspection, SMT solving, and formal AST patching."""
    method = UniversalMethod(
        name="compute_order_total",
        params=[
            UniversalParam(name="qty", type_info=UniversalType.primitive("i32")),
            UniversalParam(name="price", type_info=UniversalType.int64())
        ],
        return_type=UniversalType.int64(),
        body=[
            ExprStmt(FieldAccessExpr(target=IdentifierExpr("account"), field_name="status")),
            ReturnStmt(BinaryExpr(left=IdentifierExpr("qty"), op=BinaryOperator.ADD, right=IdentifierExpr("price")))
        ]
    )

    repaired_method, patches = SmtAutonomousRepairEngine.repair_method_ast(method, target_language="rust")
    assert len(patches) >= 2
    assert any(p.rule_name == "SMT_NUMERIC_WIDENING" for p in patches)
    assert any(p.rule_name == "SMT_NULL_GUARD_SYNTHESIS" for p in patches)

    # In Rust target, operands of return addition were promoted to CastExpr
    ret_stmt = repaired_method.body[1]
    assert isinstance(ret_stmt, ReturnStmt)
    assert isinstance(ret_stmt.value, BinaryExpr)
    assert isinstance(ret_stmt.value.left, CastExpr)
    assert ret_stmt.value.left.target_type.name == "i64"
