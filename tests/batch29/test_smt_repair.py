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


def test_smt_multiplication_overflow():
    """Verify Z3 BitVec detects potential 32-bit multiplication overflow."""
    has_overflow, patch = SmtBoundsAndOverflowSolver.check_multiplication_overflow(
        bit_width=32,
        operand_min=100000,
        operand_max=100000
    )
    assert has_overflow is True
    assert patch is not None
    assert patch.rule_name == "SMT_MULTIPLICATION_OVERFLOW"


def test_smt_division_by_zero_hazard():
    """Verify Z3 proves potential division by zero hazard."""
    has_div_zero, patch = SmtBoundsAndOverflowSolver.check_division_by_zero(0)
    assert has_div_zero is True
    assert patch is not None
    assert patch.rule_name == "SMT_DIVISION_BY_ZERO_HAZARD"

    # Non-zero constant divisor is safe
    safe_div, safe_patch = SmtBoundsAndOverflowSolver.check_division_by_zero(42)
    assert safe_div is False
    assert safe_patch is None


def test_smt_array_bounds_hazard():
    """Verify Z3 bounds checking catches out of bounds indices."""
    has_oob, patch = SmtBoundsAndOverflowSolver.check_array_bounds(index_val=10, length_val=10)
    assert has_oob is True
    assert patch is not None
    assert patch.rule_name == "SMT_OUT_OF_BOUNDS_HAZARD"

    # Negative index
    has_neg_oob, neg_patch = SmtBoundsAndOverflowSolver.check_array_bounds(index_val=-1, length_val=10)
    assert has_neg_oob is True
    assert neg_patch is not None

    # Valid index is safe
    safe_bounds, safe_patch = SmtBoundsAndOverflowSolver.check_array_bounds(index_val=5, length_val=10)
    assert safe_bounds is False
    assert safe_patch is None


def test_smt_nested_recursive_ast_repair():
    """Verify SMT engine recursively repairs nested statements inside IfElse, While, and TryCatch."""
    from elmos_polyglot_route.ast_compiler.ir import (
        IfElseStmt,
        WhileStmt,
        VarDeclStmt,
        TryCatchFinallyStmt,
        CatchClause,
    )

    nested_method = UniversalMethod(
        name="nested_pipeline",
        params=[UniversalParam(name="limit", type_info=UniversalType.primitive("i32"))],
        return_type=UniversalType.void(),
        body=[
            VarDeclStmt(name="ptr", type_info=UniversalType.optional_of(UniversalType.custom("Service"))),
            IfElseStmt(
                condition=BinaryExpr(left=IdentifierExpr("limit"), op=BinaryOperator.GT, right=LiteralExpr(0)),
                then_body=[
                    WhileStmt(
                        condition=BinaryExpr(left=IdentifierExpr("limit"), op=BinaryOperator.GT, right=LiteralExpr(1)),
                        body=[
                            # Unguarded nullable field access inside nested while loop
                            ExprStmt(FieldAccessExpr(target=IdentifierExpr("ptr"), field_name="status")),
                        ]
                    )
                ],
                else_body=[
                    TryCatchFinallyStmt(
                        try_body=[
                            # Potential 32-bit addition overflow inside try body
                            ReturnStmt(BinaryExpr(left=LiteralExpr(2000000000), op=BinaryOperator.ADD, right=LiteralExpr(2000000000)))
                        ],
                        catch_clauses=[],
                        finally_body=[]
                    )
                ]
            )
        ]
    )

    repaired_m, patches = SmtAutonomousRepairEngine.repair_method_ast(nested_method, target_language="rust")
    assert len(patches) >= 2
    assert any(p.rule_name == "SMT_NULL_GUARD_SYNTHESIS" for p in patches)
    assert any(p.rule_name == "SMT_CHECKED_ARITHMETIC_OR_WIDENING" for p in patches)


def test_smt_realistic_repair_boundary_unsolvable():
    """Honest Non-Self-Certification boundary: SMT proves certain semantic incompatibilities CANNOT be silently widened."""
    t_bool = UniversalType.primitive("bool")
    t_string = UniversalType.string_type()

    # bool cannot be automatically widened to string by numeric rank lattice
    patch = SmtTypeSolver.solve_widening_cast(t_bool, t_string)
    assert patch is None  # Accurately unsat/unsolvable by widening!

    # Assigning string to i32 is incompatible
    t_i32 = UniversalType.primitive("i32")
    compat, err_patch = SmtTypeSolver.solve_type_compatibility(t_string, t_i32)
    assert compat is False
    assert err_patch is not None
    assert err_patch.rule_name == "SMT_TYPE_INCOMPATIBLE"
