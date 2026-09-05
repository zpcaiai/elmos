"""Lifting `let` from Java source code.

Verifies that Java local variable declarations (`final T x = expr;`) correctly lift
into the canonical `let` statement, reject mutable or unannotated forms, and
emit cleanly into Go, Python, Rust, TypeScript, and C#.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "Calculation.java"
    content = (
        "public final class Calculation {\n"
        f"    {body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_java_annotated_final_local_lifts_to_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price, long tax) {\n"
        "    final long subtotal = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "java", "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"
    assert statements[1].kind == "return"


def test_java_lifted_let_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price, long tax) {\n"
        "    final long subtotal = price + tax;\n"
        "    return subtotal;\n"
        "}",
    )
    semantic = analyze(source, "java", "total")
    assert "var subtotal int64 = elmosCheckedAdd(price, tax)" in emit(semantic, "go").content
    assert "subtotal: int =" in emit(semantic, "python").content
    assert "let subtotal: i64 =" in emit(semantic, "rust").content
    assert "const subtotal: number = _elmosRequireSafeInteger(price + tax);" in emit(semantic, "typescript").content
    assert "long subtotal = checked(price + tax);" in emit(semantic, "csharp").content


def test_java_unannotated_var_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price) {\n"
        "    var subtotal = price;\n"
        "    return subtotal;\n"
        "}",
    )
    with pytest.raises(RouteError, match="JAVA_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "java", "total")


def test_java_mutable_local_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price) {\n"
        "    long subtotal = price;\n"
        "    return subtotal;\n"
        "}",
    )
    with pytest.raises(RouteError, match="JAVA_MUTABLE_LOCAL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "java", "total")


def test_java_declaration_without_value_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price) {\n"
        "    final long subtotal;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="JAVA_ANNOTATED_DECLARATION_WITHOUT_VALUE"):
        analyze(source, "java", "total")


def test_java_reassignment_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price) {\n"
        "    final long subtotal = price;\n"
        "    subtotal = price + 1;\n"
        "    return subtotal;\n"
        "}",
    )
    with pytest.raises(RouteError, match="JAVA_MUTABLE_LOCAL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "java", "total")


def test_java_unsupported_int_type_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price) {\n"
        "    final int subtotal = 1;\n"
        "    return price;\n"
        "}",
    )
    with pytest.raises(RouteError, match="JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"):
        analyze(source, "java", "total")


def test_java_multiple_sequential_bindings(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long scale(long price, long factor) {\n"
        "    final long subtotal = price * factor;\n"
        "    final long totalWithTax = subtotal + 10;\n"
        "    return totalWithTax;\n"
        "}",
    )
    semantic = analyze(source, "java", "scale")
    body = semantic.functions[0].body
    assert len(body) == 3
    assert body[0].kind == "let"
    assert body[0].name == "subtotal"
    assert body[1].kind == "let"
    assert body[1].name == "totalWithTax"
    assert body[2].kind == "return"


def test_java_shadowing_parameter_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long total(long price) {\n"
        "    final long price = 10;\n"
        "    return price;\n"
        "}",
    )
    semantic = analyze(source, "java", "total")
    with pytest.raises(RouteError, match="LET_NAME_ALREADY_BOUND:price"):
        types.check(semantic)


def test_java_missing_symbol_preserves_the_native_failure(tmp_path: Path) -> None:
    source = tmp_path / "Subject.java"
    source.write_text(
        "public final class Subject { public static long calculate(long value) { return value; } }\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RouteError,
        match="^FUNCTION_NOT_FOUND:__elmos_missing_function__$",
    ):
        analyze(source, "java", "__elmos_missing_function__")
