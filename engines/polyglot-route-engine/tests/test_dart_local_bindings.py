"""Lifting `let` and `assign` from Dart / Flutter source code.

Verifies that Dart local variable declarations (`final int x = expr;` and `int x = expr;`)
correctly lift into canonical `let` statements, assignments (`x = expr;`, `x += expr;`, `x++`)
lift into `assign`, parameter reassignment is rejected, constant reassignment is rejected,
undeclared assignments are rejected, and lifted structures emit cleanly across targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.source_analyzer import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.dart"
    content = (
        "int total(int price, int tax) {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _source_unary(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.dart"
    content = (
        "int total(int price) {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_dart_annotated_final_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  final int subtotal = price + tax;\n"
        "  return subtotal;",
    )
    semantic = analyze(source, "flutter", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_dart_annotated_mutable_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int subtotal = price + tax;\n"
        "  return subtotal;",
    )
    semantic = analyze(source, "flutter", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_dart_mutable_local_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int subtotal = price;\n"
        "  subtotal = price + tax;\n"
        "  return subtotal;",
    )
    semantic = analyze(source, "flutter", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].name == "subtotal"
    assert statements[1].expression is not None
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "return"


def test_dart_compound_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int subtotal = price;\n"
        "  subtotal += tax;\n"
        "  subtotal -= 1;\n"
        "  subtotal *= 2;\n"
        "  subtotal ~/= 3;\n"
        "  subtotal %= 5;\n"
        "  return subtotal;",
    )
    semantic = analyze(source, "flutter", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "assign"
    assert statements[2].expression.operator == "-"
    assert statements[3].kind == "assign"
    assert statements[3].expression.operator == "*"
    assert statements[4].kind == "assign"
    assert statements[4].expression.operator == "/"
    assert statements[5].kind == "assign"
    assert statements[5].expression.operator == "%"


def test_dart_postfix_and_prefix_increment_lifts(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "  int count = price;\n"
        "  count++;\n"
        "  ++count;\n"
        "  count--;\n"
        "  --count;\n"
        "  return count;",
    )
    semantic = analyze(source, "flutter", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].expression.operator == "+"
    assert statements[1].expression.right.value == 1
    assert statements[2].kind == "assign"
    assert statements[2].expression.operator == "+"
    assert statements[3].kind == "assign"
    assert statements[3].expression.operator == "-"
    assert statements[4].kind == "assign"
    assert statements[4].expression.operator == "-"


def test_dart_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  price = price + 1;\n"
        "  return price;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price$",
    ):
        analyze(source, "flutter", "total")


def test_dart_constant_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  final int subtotal = price;\n"
        "  subtotal = subtotal + 1;\n"
        "  return subtotal;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:subtotal$",
    ):
        analyze(source, "flutter", "total")


def test_dart_undeclared_assignment_target_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  unknown = 42;\n"
        "  return price;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_ASSIGNMENT_TARGET_NOT_DECLARED:unknown$",
    ):
        analyze(source, "flutter", "total")


def test_dart_assignment_type_mismatch_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int subtotal = price;\n"
        "  subtotal = 3.14;\n"
        "  return subtotal;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_ASSIGNMENT_TYPE_MISMATCH:integer:number$",
    ):
        analyze(source, "flutter", "total")


def test_dart_unannotated_var_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  var subtotal = price;\n"
        "  return subtotal;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_EXPLICIT_LOCAL_TYPE_REQUIRED$",
    ):
        analyze(source, "flutter", "total")


def test_dart_local_without_initializer_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int subtotal;\n"
        "  return price;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_LOCAL_INITIALIZER_REQUIRED$",
    ):
        analyze(source, "flutter", "total")


def test_dart_lifted_let_and_assign_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int acc = price;\n"
        "  acc += tax;\n"
        "  return acc;",
    )
    semantic = analyze(source, "flutter", "total")
    # TypeScript
    ts_code = emit(semantic, "typescript").content
    assert "let acc: number = price;" in ts_code
    assert "acc = _elmosRequireSafeInteger(" in ts_code
    assert "acc + tax" in ts_code
    # Python
    py_code = emit(semantic, "python").content
    assert "acc: int = price" in py_code
    assert "acc = _elmos_checked_add(acc, tax)" in py_code
    # Go
    go_code = emit(semantic, "go").content
    assert "var acc int64 = price" in go_code
    assert "acc = elmosCheckedAdd(acc, tax)" in go_code
    # Rust
    rs_code = emit(semantic, "rust").content
    assert "let mut acc: i64 = price;" in rs_code
    assert "acc = (acc).checked_add(tax)" in rs_code
    # Flutter / Dart
    dart_code = emit(semantic, "flutter").content
    assert "int acc = price;" in dart_code
    assert "acc = _elmosCheckedAdd(acc, tax);" in dart_code

    # Relift emitted Flutter code
    target_path = tmp_path / "migrated.dart"
    target_path.write_text(dart_code, encoding="utf-8")
    relifted = analyze(target_path, "flutter", "total", emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[0].kind == "let"
    assert relifted.functions[0].body[1].kind == "assign"
    assert relifted.functions[0].body[2].kind == "return"
