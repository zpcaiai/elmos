"""Lifting `let` and `assign` from Kotlin source code.

Verifies that Kotlin local variable declarations (`val x: Long = expr` and `var x: Long = expr`)
correctly lift into canonical `let` statements, assignments (`x = expr`, `x += expr`, `x++`)
lift into `assign`, parameter reassignment is rejected, constant reassignment is rejected,
undeclared assignments are rejected, and lifted structures emit cleanly across targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.kt"
    content = (
        "fun total(price: Long, tax: Long): Long {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _source_unary(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.kt"
    content = (
        "fun total(price: Long): Long {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_kotlin_annotated_val_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    val subtotal: Long = price + tax\n"
        "    return subtotal",
    )
    semantic = analyze(source, "kotlin", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_kotlin_annotated_var_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Long = price + tax\n"
        "    return subtotal",
    )
    semantic = analyze(source, "kotlin", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_kotlin_mutable_local_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Long = price\n"
        "    subtotal = price + tax\n"
        "    return subtotal",
    )
    semantic = analyze(source, "kotlin", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].name == "subtotal"
    assert statements[1].expression is not None
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "return"


def test_kotlin_compound_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Long = price\n"
        "    subtotal += tax\n"
        "    subtotal -= 1L\n"
        "    subtotal *= 2L\n"
        "    subtotal /= 3L\n"
        "    subtotal %= 5L\n"
        "    return subtotal",
    )
    semantic = analyze(source, "kotlin", "total")
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


def test_kotlin_postfix_and_prefix_increment_lifts(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    var count: Long = price\n"
        "    count++\n"
        "    ++count\n"
        "    count--\n"
        "    --count\n"
        "    return count",
    )
    semantic = analyze(source, "kotlin", "total")
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


def test_kotlin_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    price = price + 1L\n"
        "    return price",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price$",
    ):
        analyze(source, "kotlin", "total")


def test_kotlin_constant_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    val subtotal: Long = price\n"
        "    subtotal = subtotal + 1L\n"
        "    return subtotal",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:subtotal$",
    ):
        analyze(source, "kotlin", "total")


def test_kotlin_undeclared_assignment_target_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    unknown = 42L\n"
        "    return price",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_ASSIGNMENT_TARGET_NOT_DECLARED:unknown$",
    ):
        analyze(source, "kotlin", "total")


def test_kotlin_unannotated_val_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    val subtotal = price\n"
        "    return subtotal",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_EXPLICIT_TYPE_REQUIRED$",
    ):
        analyze(source, "kotlin", "total")


def test_kotlin_multiple_sequential_bindings(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    val subtotal: Long = price * 2L\n"
        "    var totalWithTax: Long = subtotal + tax\n"
        "    totalWithTax += 5L\n"
        "    return totalWithTax",
    )
    semantic = analyze(source, "kotlin", "total")
    body = semantic.functions[0].body
    assert len(body) == 4
    assert body[0].kind == "let"
    assert body[0].name == "subtotal"
    assert body[1].kind == "let"
    assert body[1].name == "totalWithTax"
    assert body[2].kind == "assign"
    assert body[2].name == "totalWithTax"
    assert body[3].kind == "return"


def test_kotlin_lifted_let_and_assign_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var acc: Long = price\n"
        "    acc += tax\n"
        "    return acc",
    )
    semantic = analyze(source, "kotlin", "total")

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

    # Kotlin
    kt_code = emit(semantic, "kotlin").content
    assert "var acc: Long = price" in kt_code
    assert "acc = Math.addExact(acc, tax)" in kt_code

    # Relift emitted Kotlin code
    target_path = tmp_path / "migrated.kt"
    target_path.write_text(kt_code, encoding="utf-8")
    relifted = analyze(target_path, "kotlin", "total", emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[0].kind == "let"
    assert relifted.functions[0].body[1].kind == "assign"
    assert relifted.functions[0].body[2].kind == "return"
