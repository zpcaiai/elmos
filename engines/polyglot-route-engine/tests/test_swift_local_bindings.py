"""Lifting `let` and `assign` from Swift source code.

Verifies that Swift local variable declarations (`let x: Int64 = expr` and `var x: Int64 = expr`)
correctly lift into canonical `let` statements, assignments (`x = expr`, `x += expr`)
lift into `assign`, parameter reassignment is rejected, constant reassignment is rejected,
undeclared assignments are rejected, and lifted structures emit cleanly across targets.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, target_ir_view
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze

SWIFTC = shutil.which("swiftc")
pytestmark = pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.swift"
    content = (
        "func total(_ price: Int64, _ tax: Int64) -> Int64 {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_swift_annotated_let_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    let subtotal: Int64 = price + tax\n"
        "    return subtotal",
    )
    semantic = analyze(source, "swift", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_swift_annotated_var_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Int64 = price + tax\n"
        "    return subtotal",
    )
    semantic = analyze(source, "swift", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_swift_mutable_local_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Int64 = price\n"
        "    subtotal = price + tax\n"
        "    return subtotal",
    )
    semantic = analyze(source, "swift", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "assign"
    assert statements[1].name == "subtotal"
    assert statements[1].expression is not None
    assert statements[1].expression.operator == "+"
    assert statements[2].kind == "return"


def test_swift_compound_assignment_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Int64 = price\n"
        "    subtotal += tax\n"
        "    subtotal -= 1\n"
        "    subtotal *= 2\n"
        "    subtotal /= 3\n"
        "    subtotal %= 5\n"
        "    return subtotal",
    )
    semantic = analyze(source, "swift", "total")
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


def test_swift_parameter_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    price = price + 1\n"
        "    return price",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:price$",
    ):
        analyze(source, "swift", "total")


def test_swift_constant_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    let subtotal: Int64 = price\n"
        "    subtotal = subtotal + 1\n"
        "    return subtotal",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:subtotal$",
    ):
        analyze(source, "swift", "total")


def test_swift_undeclared_assignment_target_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    unknown = 42\n"
        "    return price",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_ASSIGNMENT_TARGET_NOT_DECLARED:unknown$",
    ):
        analyze(source, "swift", "total")


def test_swift_unannotated_let_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    let subtotal = price\n"
        "    return subtotal",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_EXPLICIT_TYPE_REQUIRED$",
    ):
        analyze(source, "swift", "total")


def test_swift_assignment_type_mismatch_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var subtotal: Int64 = price\n"
        '    subtotal = "hello"\n'
        "    return subtotal",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_ASSIGNMENT_TYPE_MISMATCH$",
    ):
        analyze(source, "swift", "total")


def test_swift_multiple_sequential_bindings(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    let subtotal: Int64 = price * 2\n"
        "    var totalWithTax: Int64 = subtotal + tax\n"
        "    totalWithTax += 5\n"
        "    return totalWithTax",
    )
    semantic = analyze(source, "swift", "total")
    body = semantic.functions[0].body
    assert len(body) == 4
    assert body[0].kind == "let"
    assert body[0].name == "subtotal"
    assert body[1].kind == "let"
    assert body[1].name == "totalWithTax"
    assert body[2].kind == "assign"
    assert body[2].name == "totalWithTax"
    assert body[3].kind == "return"


def test_swift_lifted_let_and_assign_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var acc: Int64 = price\n"
        "    acc += tax\n"
        "    return acc",
    )
    semantic = analyze(source, "swift", "total")

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

    # Swift
    swift_code = emit(semantic, "swift").content
    assert "var acc: Int64 = price" in swift_code
    assert "acc = (acc + tax)" in swift_code

    # Relift emitted Swift code
    plan = plan_identifiers(semantic, "swift")
    symbol = target_ir_view(semantic, plan).functions[0].name
    target_path = tmp_path / "migrated.swift"
    target_path.write_text(swift_code, encoding="utf-8")
    relifted = analyze(target_path, "swift", symbol, emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[0].kind == "let"
    assert relifted.functions[0].body[1].kind == "assign"
    assert relifted.functions[0].body[2].kind == "return"
