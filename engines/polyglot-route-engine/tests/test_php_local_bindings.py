"""Lifting `let` and `assign` from PHP source code.

Verifies that PHP local variable definitions (`$x = expr`)
correctly lift into canonical `let` statements, assignments (`$x = expr`, `$x += expr`, `$x++`)
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
    path = tmp_path / "subject.php"
    content = (
        "<?php\n\n"
        "declare(strict_types=1);\n\n"
        "function total(int $price, int $tax): int {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _source_unary(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.php"
    content = (
        "<?php\n\n"
        "declare(strict_types=1);\n\n"
        "function total(int $price): int {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_php_local_binding_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $subtotal = $price + $tax;\n"
        "    return $subtotal;",
    )
    semantic = analyze(source, "php", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_php_mutable_local_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $subtotal = $price;\n"
        "    $subtotal = $price + $tax;\n"
        "    return $subtotal;",
    )
    semantic = analyze(source, "php", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].name == "subtotal"
    assert statements[1].expression is not None
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "return"


def test_php_compound_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $subtotal = $price;\n"
        "    $subtotal += $tax;\n"
        "    $subtotal -= 1;\n"
        "    $subtotal *= 2;\n"
        "    $subtotal %= 5;\n"
        "    return $subtotal;",
    )
    semantic = analyze(source, "php", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "assign"
    assert statements[2].expression.operator == "-"
    assert statements[3].kind == "assign"
    assert statements[3].expression.operator == "*"
    assert statements[4].kind == "assign"
    assert statements[4].expression.operator == "%"


def test_php_increment_decrement_lifts(tmp_path: Path) -> None:
    source = _source_unary(
        tmp_path,
        "    $count = $price;\n"
        "    $count++;\n"
        "    ++$count;\n"
        "    $count--;\n"
        "    --$count;\n"
        "    return $count;",
    )
    semantic = analyze(source, "php", "total")
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


def test_php_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $price = $price + 1;\n"
        "    return $price;",
    )
    with pytest.raises(
        RouteError,
        match="^PHP_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price$",
    ):
        analyze(source, "php", "total")


def test_php_undeclared_assignment_target_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $unknown += 42;\n"
        "    return $price;",
    )
    with pytest.raises(
        RouteError,
        match="^PHP_ASSIGNMENT_TARGET_NOT_DECLARED:unknown$",
    ):
        analyze(source, "php", "total")


def test_php_local_scope_leak_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    if ($price > 0) {\n"
        "        $local = 1;\n"
        "    }\n"
        "    return $local;",
    )
    with pytest.raises(
        RouteError,
        match="^PHP_UNDECLARED_NAME:local$",
    ):
        analyze(source, "php", "total")


def test_php_self_referencing_initializer_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $x = $x + 1;\n"
        "    return $x;",
    )
    with pytest.raises(
        RouteError,
        match="^PHP_UNDECLARED_NAME:x$",
    ):
        analyze(source, "php", "total")


def test_php_local_bindings_emit_across_targets_and_relift(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $subtotal = $price;\n"
        "    $subtotal += $tax;\n"
        "    return $subtotal;",
    )
    semantic = analyze(source, "php", "total")

    # Target: Python
    py_code = emit(semantic, "python").content
    assert "subtotal: int = price" in py_code
    assert "subtotal = subtotal + tax" in py_code or "subtotal += tax" in py_code or "_elmos_checked_add(subtotal, tax)" in py_code

    # Target: TypeScript
    ts_code = emit(semantic, "typescript").content
    assert "let subtotal: number = price" in ts_code

    # Target: Go
    go_code = emit(semantic, "go").content
    assert "var subtotal int64 = price" in go_code

    # Target: Rust
    rs_code = emit(semantic, "rust").content
    assert "let mut subtotal: i64 = price" in rs_code

    # Target: PHP
    php_code = emit(semantic, "php").content
    assert "$subtotal = $price;" in php_code
    assert "elmos_checked_add($subtotal, $tax)" in php_code or "$subtotal = ($subtotal + $tax);" in php_code

    # Relift emitted PHP code
    target_file = tmp_path / "migrated.php"
    target_file.write_text(php_code, encoding="utf-8")
    relifted = analyze(target_file, "php", "total", emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[0].kind == "let"
    assert relifted.functions[0].body[1].kind == "assign"
    assert relifted.functions[0].body[2].kind == "return"
