"""Lifting `let` and `assign` from Rust source code.

Verifies that Rust local variable declarations (`let x: i64 = expr;` and `let mut x: i64 = expr;`)
correctly lift into canonical `let` statements, assignments (`x = expr;`, `x += expr;`) lift
into `assign`, parameter reassignment is rejected, unannotated `let` is rejected, and
lifted structures emit cleanly across targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "lib.rs"
    content = f"{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def test_rust_annotated_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64, tax: i64) -> i64 {\n"
        "    let subtotal: i64 = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "rust", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_rust_mut_annotated_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64, tax: i64) -> i64 {\n"
        "    let mut subtotal: i64 = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "rust", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_rust_lifted_let_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64, tax: i64) -> i64 {\n"
        "    let subtotal: i64 = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "rust", "total")
    assert "var subtotal int64 = elmosCheckedAdd(price, tax)" in emit(semantic, "go").content
    assert "subtotal: int =" in emit(semantic, "python").content
    assert "let subtotal: i64 =" in emit(semantic, "rust").content
    assert "const subtotal: number = _elmosRequireSafeInteger(price + tax);" in emit(semantic, "typescript").content
    assert "long subtotal = checked(price + tax);" in emit(semantic, "csharp").content


def test_rust_unannotated_let_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    let subtotal = price;\n"
        "    return subtotal;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "rust", "total")


def test_rust_declaration_without_value_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    let subtotal: i64;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_ANNOTATED_DECLARATION_WITHOUT_VALUE"):
        analyze(source, "rust", "total")


def test_rust_assign_statement_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    let mut acc: i64 = 0;\n"
        "    acc = price;\n"
        "    return acc;\n"
        "}",
    )
    semantic = analyze(source, "rust", "total")
    statements = semantic.functions[0].body
    assert len(statements) == 3
    assert statements[0].kind == "let"
    assert statements[0].name == "acc"
    assert statements[1].kind == "assign"
    assert statements[1].name == "acc"
    assert statements[1].expression is not None
    assert statements[1].expression.kind == "name"
    assert statements[1].expression.value == "price"
    assert statements[2].kind == "return"


def test_rust_compound_assignment_lifts_to_binary(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    let mut acc: i64 = 0;\n"
        "    acc += price;\n"
        "    acc -= 1;\n"
        "    acc *= 2;\n"
        "    acc /= 3;\n"
        "    acc %= 4;\n"
        "    return acc;\n"
        "}",
    )
    semantic = analyze(source, "rust", "total")
    statements = semantic.functions[0].body
    assert len(statements) == 7
    expected_ops = ["+", "-", "*", "/", "%"]
    for i, op in enumerate(expected_ops, start=1):
        stmt = statements[i]
        assert stmt.kind == "assign"
        assert stmt.name == "acc"
        assert stmt.expression is not None
        assert stmt.expression.kind == "binary"
        assert stmt.expression.operator == op
        assert stmt.expression.left is not None and stmt.expression.left.value == "acc"


def test_rust_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    price = price + 1;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price"):
        analyze(source, "rust", "total")


def test_rust_parameter_compound_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    price += 1;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price"):
        analyze(source, "rust", "total")


def test_rust_undeclared_variable_assignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    acc = price;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_ASSIGNMENT_TARGET_NOT_DECLARED:acc"):
        analyze(source, "rust", "total")


def test_rust_pattern_tuple_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    let (a, b) = (1, 2);\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_PATTERN_BINDING_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "rust", "total")


def test_rust_shadowing_parameter_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn total(price: i64) -> i64 {\n"
        "    let price: i64 = 10;\n"
        "    return price;\n"
        "}",
    )
    semantic = analyze(source, "rust", "total")
    with pytest.raises(RouteError, match="LET_NAME_ALREADY_BOUND:price"):
        types.check(semantic)
