"""Lifting `let` from Go source code.

Verifies that Go local variable declarations (`var x T = expr`) correctly lift
into the canonical `let` statement, reject mutable or unannotated forms, and
emit cleanly into Java, Python, Rust, TypeScript, and C#.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "main.go"
    content = f"package main\n\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def test_go_annotated_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64, tax int64) int64 {\n"
        "    var subtotal int64 = price + tax\n"
        "    return subtotal\n"
        "}",
    )
    semantic = analyze(source, "go", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_go_lifted_let_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64, tax int64) int64 {\n"
        "    var subtotal int64 = price + tax\n"
        "    return subtotal\n"
        "}",
    )
    semantic = analyze(source, "go", "total")
    assert "final long subtotal = Math.addExact(price, tax);" in emit(semantic, "java").content
    assert "subtotal: int =" in emit(semantic, "python").content
    assert "let subtotal: i64 =" in emit(semantic, "rust").content
    assert "const subtotal: number = _elmosRequireSafeInteger(price + tax);" in emit(semantic, "typescript").content
    assert "long subtotal = checked(price + tax);" in emit(semantic, "csharp").content


def test_go_unannotated_define_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64) int64 {\n"
        "    subtotal := price\n"
        "    return subtotal\n"
        "}",
    )
    with pytest.raises(RouteError, match="GO_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "go", "total")


def test_go_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64) int64 {\n"
        "    var subtotal int64 = price\n"
        "    subtotal = price + 1\n"
        "    return subtotal\n"
        "}",
    )
    with pytest.raises(RouteError, match="GO_MUTABLE_VARIABLE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "go", "total")


def test_go_declaration_without_value_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64) int64 {\n"
        "    var subtotal int64\n"
        "    return price\n"
        "}",
    )
    with pytest.raises(RouteError, match="GO_ANNOTATED_DECLARATION_WITHOUT_VALUE"):
        analyze(source, "go", "total")


def test_go_multiple_declarations_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64) int64 {\n"
        "    var a, b int64 = 1, 2\n"
        "    return price\n"
        "}",
    )
    with pytest.raises(RouteError, match="GO_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "go", "total")


def test_go_unsupported_int_type_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64) int64 {\n"
        "    var subtotal int = 1\n"
        "    return price\n"
        "}",
    )
    with pytest.raises(RouteError, match="GO_UNSUPPORTED_TYPE:int"):
        analyze(source, "go", "total")


def test_go_multiple_sequential_bindings(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func scale(price int64, factor int64) int64 {\n"
        "    var subtotal int64 = price * factor\n"
        "    var totalWithTax int64 = subtotal + 10\n"
        "    return totalWithTax\n"
        "}",
    )
    semantic = analyze(source, "go", "scale")
    body = semantic.functions[0].body
    assert len(body) == 3
    assert body[0].kind == "let"
    assert body[0].name == "subtotal"
    assert body[1].kind == "let"
    assert body[1].name == "totalWithTax"
    assert body[2].kind == "return"


def test_go_shadowing_parameter_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "func total(price int64) int64 {\n"
        "    var price int64 = 10\n"
        "    return price\n"
        "}",
    )
    semantic = analyze(source, "go", "total")
    with pytest.raises(RouteError, match="LET_NAME_ALREADY_BOUND:price"):
        types.check(semantic)
