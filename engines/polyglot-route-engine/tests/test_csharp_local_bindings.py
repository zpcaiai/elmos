"""Lifting `let` and `assign` from C# source code.

Verifies that C# local variable declarations (`long x = expr;`) correctly lift
into canonical `let` statements, assignments (`x = expr;`) lift into `assign`,
parameter reassignment is rejected, unannotated `var` is rejected, and
lifted structures emit cleanly across targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "Calculation.cs"
    content = (
        "public static class Calculation {\n"
        f"    {body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_csharp_annotated_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price, long tax) {\n"
        "    long subtotal = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "csharp", "Total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_csharp_lifted_let_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price, long tax) {\n"
        "    long subtotal = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "csharp", "Total")
    assert "var subtotal int64 = elmosCheckedAdd(price, tax)" in emit(semantic, "go").content
    assert "subtotal: int =" in emit(semantic, "python").content
    assert "let subtotal: i64 =" in emit(semantic, "rust").content
    assert "const subtotal: number = _elmosRequireSafeInteger(price + tax);" in emit(semantic, "typescript").content
    assert "long subtotal = checked(price + tax);" in emit(semantic, "csharp").content


def test_csharp_unannotated_var_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    var subtotal = price;\n"
        "    return subtotal;\n"
        "}",
    )
    with pytest.raises(RouteError, match="CSHARP_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "csharp", "Total")


def test_csharp_declaration_without_value_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    long subtotal;\n"
        "    return price;\n"
        "}",
    )
    # Uninitialized local in C# causes compiler error CS0165 or CSHARP_ANNOTATED_DECLARATION_WITHOUT_VALUE
    with pytest.raises(RouteError):
        analyze(source, "csharp", "Total")


def test_csharp_assign_statement_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    long acc = 0;\n"
        "    acc = price;\n"
        "    return acc;\n"
        "}",
    )
    semantic = analyze(source, "csharp", "Total")
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


def test_csharp_compound_assign_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    long acc = 0;\n"
        "    acc += price;\n"
        "    return acc;\n"
        "}",
    )
    semantic = analyze(source, "csharp", "Total")
    statements = semantic.functions[0].body
    assert statements[1].kind == "assign"
    assert statements[1].name == "acc"
    expr = statements[1].expression
    assert expr is not None
    assert expr.kind == "binary"
    assert expr.operator == "+"
    assert expr.left is not None and expr.left.value == "acc"
    assert expr.right is not None and expr.right.value == "price"


def test_csharp_inc_dec_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    long acc = price;\n"
        "    acc++;\n"
        "    acc--;\n"
        "    return acc;\n"
        "}",
    )
    semantic = analyze(source, "csharp", "Total")
    statements = semantic.functions[0].body
    assert statements[1].kind == "assign"
    assert statements[1].name == "acc"
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "assign"
    assert statements[2].name == "acc"
    assert statements[2].expression.operator == "-"


def test_csharp_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    price = price + 1;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="CSHARP_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price"):
        analyze(source, "csharp", "Total")


def test_csharp_undeclared_assign_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long Total(long price) {\n"
        "    undeclared = 1;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError):
        analyze(source, "csharp", "Total")
