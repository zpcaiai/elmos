"""Lifting `let` and `assign` from TypeScript source code.

Verifies that TypeScript local variable declarations (`const x: number = expr;` and `let x: number = expr;`)
correctly lift into canonical `let` statements, assignments (`x = expr;`, `x += expr;`, `x++`) lift
into `assign`, parameter reassignment is rejected, unannotated declarations are rejected, and
lifted structures emit cleanly across targets and re-analyze as emitted targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.ts"
    content = (
        "export function total(price: number, tax: number): number {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _source_unary(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.ts"
    content = (
        "export function total(price: number): number {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_typescript_annotated_const_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const subtotal: number = price + tax;\n"
        "    return subtotal;",
    )
    semantic = analyze(source, "typescript", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type in ("integer", "number")
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_typescript_annotated_let_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    let subtotal: number = price + tax;\n"
        "    return subtotal;",
    )
    semantic = analyze(source, "typescript", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type in ("integer", "number")
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_typescript_lifted_let_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    let subtotal: number = price + tax;\n"
        "    return subtotal;",
    )
    semantic = analyze(source, "typescript", "total")
    for target in ("java", "go", "python", "rust", "csharp", "typescript"):
        content = emit(semantic, target).content
        assert "subtotal" in content


def test_typescript_unannotated_let_rejected(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    let subtotal = price;\n"
        "    return subtotal;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "typescript", "total")


def test_typescript_declaration_without_value_rejected(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    let subtotal: number;\n"
        "    return price;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_ANNOTATED_DECLARATION_WITHOUT_VALUE"):
        analyze(source, "typescript", "total")


def test_typescript_var_rejected(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    var subtotal: number = price;\n"
        "    return subtotal;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_VAR_DECLARATION_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "typescript", "total")


def test_typescript_assign_statement_lifts(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    let acc: number = 0;\n"
        "    acc = price;\n"
        "    return acc;",
    )
    semantic = analyze(source, "typescript", "total")
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


def test_typescript_compound_assign_lifts(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    let acc: number = 0;\n"
        "    acc += price;\n"
        "    return acc;",
    )
    semantic = analyze(source, "typescript", "total")
    statements = semantic.functions[0].body
    assert statements[1].kind == "assign"
    assert statements[1].name == "acc"
    expr = statements[1].expression
    assert expr is not None
    assert expr.kind == "binary"
    assert expr.operator == "+"
    assert expr.left is not None and expr.left.value == "acc"
    assert expr.right is not None and expr.right.value == "price"


def test_typescript_inc_dec_lifts(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    let acc: number = price;\n"
        "    acc++;\n"
        "    acc--;\n"
        "    return acc;",
    )
    semantic = analyze(source, "typescript", "total")
    statements = semantic.functions[0].body
    assert statements[1].kind == "assign"
    assert statements[1].name == "acc"
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "assign"
    assert statements[2].name == "acc"
    assert statements[2].expression.operator == "-"


def test_typescript_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    price = price + 1;\n"
        "    return price;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price"):
        analyze(source, "typescript", "total")


def test_typescript_undeclared_variable_assignment_rejected(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    acc = price;\n"
        "    return price;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_ASSIGNMENT_TARGET_NOT_DECLARED:acc"):
        analyze(source, "typescript", "total")


def test_typescript_constant_reassignment_rejected(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    const acc: number = 0;\n"
        "    acc = price;\n"
        "    return acc;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:acc"):
        analyze(source, "typescript", "total")


def test_typescript_emitted_target_reanalysis_with_assign(tmp_path: Path) -> None:
    path = tmp_path / "subject.ts"
    content = (
        "type integer = number;\n"
        "export function total(price: integer): integer {\n"
        "    let acc: integer = 0;\n"
        "    acc = price;\n"
        "    return acc;\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    semantic = analyze(path, "typescript", "total")
    emitted = emit(semantic, "typescript").content
    target_path = tmp_path / "emitted.ts"
    target_path.write_text(emitted, encoding="utf-8")
    reanalyzed = analyze(target_path, "typescript", "total", emitted_target=True)
    assert len(reanalyzed.functions[0].body) == len(semantic.functions[0].body)
    assert reanalyzed.functions[0].body[0].kind == "let"
    assert reanalyzed.functions[0].body[1].kind == "assign"
