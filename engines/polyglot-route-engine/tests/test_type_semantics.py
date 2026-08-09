"""Regression tests for canonical-type -> target-type/operator fidelity.

Every case here was first reproduced end to end against the real toolchains
(javac/java 21, CPython, Node) on the *previous* emitter, which mapped the
canonical operators one-to-one into every target:

    IR: divide(a: integer, b: integer) -> integer { return a / b; }
    java   -> divide(7, 2) == 3        python -> divide(7, 2) == 3.5
    IR: rem(a: integer, b: integer) -> integer { return a % b; }
    java   -> rem(-7, 2) == -1         python -> rem(-7, 2) == 1
    IR: same(a: string, b: string) -> boolean { return a == b; }
    java   -> false for equal, non-identical strings; everywhere else true
    IR: big() -> integer { return 9007199254740993; }
    java   -> does not compile ("integer number too large")
    ts     -> silently emits 9007199254740992

These tests need no toolchain: they assert on the emitted text, and execute
the emitted Python (the one target this process can run directly) against the
Java/C#/TypeScript reference results.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError, SemanticIR
from elmos_polyglot_route.python_analyzer import analyze_python


def _ir(function: dict[str, Any]) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Fixture.java",
            "analyzer": "test",
            "analyzer_version": "0",
            "functions": [function],
            "diagnostics": [],
        }
    )


def _name(value: str) -> dict[str, Any]:
    return {"kind": "name", "value": value}


def _binary(operator: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def _function(
    name: str,
    parameters: list[tuple[str, str]],
    return_type: str,
    expression: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "parameters": [{"name": n, "type": t} for n, t in parameters],
        "return_type": return_type,
        "body": [{"kind": "return", "expression": expression}],
    }


def _run_python(source: str, name: str, *args: Any) -> Any:
    namespace: dict[str, Any] = {}
    exec(compile(source, "migrated.py", "exec"), namespace)  # noqa: S102 - the emitted module is the unit under test
    return namespace[name](*args)


_INTEGER_DIVIDE = _function(
    "divide", [("a", "integer"), ("b", "integer")], "integer", _binary("/", _name("a"), _name("b"))
)
_INTEGER_REMAINDER = _function(
    "rem", [("a", "integer"), ("b", "integer")], "integer", _binary("%", _name("a"), _name("b"))
)
_FLOAT_REMAINDER = _function(
    "rem", [("a", "number"), ("b", "number")], "number", _binary("%", _name("a"), _name("b"))
)
_STRING_EQUALS = _function(
    "same", [("a", "string"), ("b", "string")], "boolean", _binary("==", _name("a"), _name("b"))
)


# --------------------------------------------------------------------------
# Integer division: truncating toward zero in every target.
# --------------------------------------------------------------------------


def test_integer_division_is_checked_in_java_and_csharp() -> None:
    # Both truncate toward zero natively, but rule R2 also makes a zero divisor
    # and Long.MIN_VALUE / -1 errors. C# throws on both without help; Java's
    # `%` and `/` do not, so the emitted class carries its own guard.
    assert "return Migrated.elmosCheckedDiv(a, b);" in emit(_ir(_INTEGER_DIVIDE), "java").content
    assert "private static long elmosCheckedDiv(long left, long right)" in emit(
        _ir(_INTEGER_DIVIDE), "java"
    ).content
    assert "return checked(a / b);" in emit(_ir(_INTEGER_DIVIDE), "csharp").content


def test_integer_division_truncates_and_rejects_a_zero_divisor_in_typescript() -> None:
    content = emit(_ir(_INTEGER_DIVIDE), "typescript").content
    # Math.trunc alone answered Infinity for a zero divisor -- a silent wrong
    # value where every other target failed.
    assert "Math.trunc(a / _elmosRequireNonZero(b))" in content
    assert "function _elmosRequireNonZero(value: number): number" in content


@pytest.mark.parametrize(("a", "b", "expected"), [(7, 2, 3), (-7, 2, -3), (7, -2, -3), (-7, -2, 3), (6, 3, 2)])
def test_emitted_python_integer_division_matches_java(a: int, b: int, expected: int) -> None:
    source = emit(_ir(_INTEGER_DIVIDE), "python").content
    assert "a / b" not in source  # the defect: true division, and a float result
    result = _run_python(source, "divide", a, b)
    assert result == expected
    assert isinstance(result, int), "an `integer` return must not come back as a float"


# --------------------------------------------------------------------------
# Remainder: sign of the dividend in every target.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("a", "b", "expected"), [(-7, 2, -1), (7, -2, 1), (7, 2, 1), (-7, -2, -1)])
def test_emitted_python_integer_remainder_matches_java(a: int, b: int, expected: int) -> None:
    source = emit(_ir(_INTEGER_REMAINDER), "python").content
    result = _run_python(source, "rem", a, b)
    assert result == expected
    assert isinstance(result, int)


def test_emitted_python_float_remainder_matches_java() -> None:
    source = emit(_ir(_FLOAT_REMAINDER), "python").content
    # Java/C#/TypeScript: -7.5 % 2 == -1.5. Python's own % answers 0.5.
    assert _run_python(source, "rem", -7.5, 2.0) == -1.5


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("java", "return Migrated.elmosCheckedMod(a, b);"),
        ("csharp", "return checked(a % b);"),
        ("typescript", "a % _elmosRequireNonZero(b)"),
    ],
)
def test_remainder_keeps_the_dividend_sign_and_rejects_a_zero_divisor(
    language: str, expected: str
) -> None:
    assert expected in emit(_ir(_INTEGER_REMAINDER), language).content


# --------------------------------------------------------------------------
# String equality: value equality in every target.
# --------------------------------------------------------------------------


def test_string_equality_uses_equals_in_java() -> None:
    content = emit(_ir(_STRING_EQUALS), "java").content
    assert "a.equals(b)" in content
    assert "a == b" not in content


def test_string_inequality_negates_equals_in_java() -> None:
    function = _function(
        "differs", [("a", "string"), ("b", "string")], "boolean", _binary("!=", _name("a"), _name("b"))
    )
    assert "(!a.equals(b))" in emit(_ir(function), "java").content


def test_typescript_uses_strict_equality() -> None:
    assert "(a === b)" in emit(_ir(_STRING_EQUALS), "typescript").content


def test_numeric_equality_is_untouched_in_java() -> None:
    function = _function(
        "same", [("a", "integer"), ("b", "integer")], "boolean", _binary("==", _name("a"), _name("b"))
    )
    assert "(a == b)" in emit(_ir(function), "java").content


def test_string_ordering_fails_closed() -> None:
    # Java orders by UTF-16 code unit and Python by code point: the two
    # disagree above the BMP, so no emitted comparison is faithful in both.
    function = _function(
        "before", [("a", "string"), ("b", "string")], "boolean", _binary("<", _name("a"), _name("b"))
    )
    for language in ("java", "python", "csharp", "typescript"):
        with pytest.raises(RouteError, match="STRING_ORDERING_OUTSIDE_CERTIFIED_SUBSET"):
            emit(_ir(function), language)


# --------------------------------------------------------------------------
# Literals.
# --------------------------------------------------------------------------


def _constant(value: Any, return_type: str) -> SemanticIR:
    return _ir(_function("value", [], return_type, {"kind": "literal", "value": value}))


@pytest.mark.parametrize("language", ["java", "csharp"])
def test_integer_literal_beyond_int32_gets_the_long_suffix(language: str) -> None:
    # Without the suffix javac rejects the source outright:
    # "error: integer number too large".
    assert "return 9007199254740993L;" in emit(_constant(9007199254740993, "integer"), language).content
    assert "return 2147483647;" in emit(_constant(2147483647, "integer"), language).content


def test_integer_literal_beyond_the_typescript_safe_range_fails_closed() -> None:
    with pytest.raises(RouteError, match="INTEGER_LITERAL_UNSAFE_FOR_TYPESCRIPT"):
        emit(_constant(9007199254740993, "integer"), "typescript")
    assert "9007199254740991" in emit(_constant(2**53 - 1, "integer"), "typescript").content


@pytest.mark.parametrize("language", ["java", "python", "csharp", "typescript"])
def test_integer_literal_beyond_int64_fails_closed(language: str) -> None:
    with pytest.raises(RouteError, match="INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE"):
        emit(_constant(2**63, "integer"), language)


@pytest.mark.parametrize("language", ["java", "python", "csharp", "typescript"])
def test_non_finite_float_literal_fails_closed(language: str) -> None:
    with pytest.raises(RouteError, match="NON_FINITE_LITERAL_OUTSIDE_CERTIFIED_SUBSET"):
        emit(_constant(float("inf"), "number"), language)


# --------------------------------------------------------------------------
# The type checker itself.
# --------------------------------------------------------------------------


def test_mixed_string_and_numeric_arithmetic_fails_closed() -> None:
    function = _function(
        "mix", [("a", "string"), ("b", "integer")], "string", _binary("+", _name("a"), _name("b"))
    )
    with pytest.raises(RouteError, match="OPERAND_TYPE_MISMATCH"):
        emit(_ir(function), "java")


def test_returning_a_float_expression_from_an_integer_function_fails_closed() -> None:
    function = _function(
        "narrow", [("a", "integer"), ("b", "number")], "integer", _binary("*", _name("a"), _name("b"))
    )
    with pytest.raises(RouteError, match="RETURN_TYPE_MISMATCH"):
        emit(_ir(function), "java")


def test_integer_widens_to_number_on_return() -> None:
    function = _function(
        "widen", [("a", "integer"), ("b", "integer")], "number", _binary("+", _name("a"), _name("b"))
    )
    assert "double widen(long a, long b)" in emit(_ir(function), "java").content


def test_unknown_name_fails_closed() -> None:
    function = _function("ghost", [("a", "integer")], "integer", _name("b"))
    with pytest.raises(RouteError, match="UNDECLARED_NAME:b"):
        emit(_ir(function), "java")


# --------------------------------------------------------------------------
# TypeScript integer range: a `number` stops being exact past 2^53-1, so an
# `integer` value arriving at (or leaving) a TypeScript function is guarded
# rather than silently rounded. Literals are already rejected at emission;
# this covers the runtime path.
# --------------------------------------------------------------------------


def test_typescript_guards_integer_parameters_and_returns() -> None:
    content = emit(_ir(_INTEGER_DIVIDE), "typescript").content
    assert "function _elmosRequireSafeInteger(value: number): number {" in content
    assert "    _elmosRequireSafeInteger(a);" in content
    assert "    _elmosRequireSafeInteger(b);" in content
    assert "return _elmosRequireSafeInteger(" in content


def test_typescript_number_only_functions_carry_no_guard() -> None:
    function = _function(
        "ratio", [("a", "number"), ("b", "number")], "number", _binary("/", _name("a"), _name("b"))
    )
    content = emit(_ir(function), "typescript").content
    assert "_elmosRequireSafeInteger" not in content
    # A float divisor still gets the R2 guard, so the helper precedes the
    # function; the safe-integer guard is what stays out of a number-only unit.
    assert "export function ratio" in content
    assert "_elmosRequireNonZero(b)" in content


@pytest.mark.parametrize("language", ["java", "python", "csharp"])
def test_the_guard_is_typescript_only(language: str) -> None:
    # long/int hold the whole canonical range exactly; a guard would be noise.
    assert "_elmosRequireSafeInteger" not in emit(_ir(_INTEGER_DIVIDE), language).content


# --------------------------------------------------------------------------
# Lifting *from* Python: the two operators whose Python meaning is not the
# canonical one must not be lifted as if they were.
# --------------------------------------------------------------------------


def _python_source(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "source.py"
    source.write_text(body, encoding="utf-8")
    return source


def test_python_true_division_on_integers_is_not_lifted_as_truncating_division(tmp_path: Path) -> None:
    # `7 / 2` is 3.5 in Python. Lifting it as canonical `/` would have emitted
    # `a / b` into Java, where it answers 3.
    source = _python_source(tmp_path, "def divide(a: int, b: int) -> int:\n    return a / b\n")
    with pytest.raises(RouteError, match="PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET"):
        analyze_python(source, "divide")


def test_python_float_division_is_still_lifted(tmp_path: Path) -> None:
    source = _python_source(tmp_path, "def divide(a: float, b: float) -> float:\n    return a / b\n")
    semantic = analyze_python(source, "divide")
    # Float division stays the plain operator; only the divisor is guarded,
    # because Python raises on 0.0 where every other target answers Infinity.
    assert "(a / Migrated.elmosNonZero(b))" in emit(semantic, "java").content


def test_python_modulo_is_not_lifted(tmp_path: Path) -> None:
    # Python's % follows the sign of the divisor for ints *and* floats.
    source = _python_source(tmp_path, "def rem(a: int, b: int) -> int:\n    return a % b\n")
    with pytest.raises(RouteError, match="PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET"):
        analyze_python(source, "rem")


def test_python_floor_division_stays_outside_the_subset(tmp_path: Path) -> None:
    source = _python_source(tmp_path, "def divide(a: int, b: int) -> int:\n    return a // b\n")
    with pytest.raises(RouteError, match="PYTHON_UNSUPPORTED_EXPRESSION"):
        analyze_python(source, "divide")


def test_python_addition_still_lifts_and_emits(tmp_path: Path) -> None:
    source = _python_source(
        tmp_path,
        "def calculate(subtotal: int, tax: int) -> int:\n"
        "    if subtotal < 0:\n"
        "        return 0\n"
        "    return subtotal + tax\n",
    )
    semantic = analyze_python(source, "calculate")
    assert "public static long calculate(long subtotal, long tax)" in emit(semantic, "java").content


# --------------------------------------------------------------------------
# The behaviour harnesses themselves must not corrupt the case they assert.
# --------------------------------------------------------------------------


def test_typescript_harness_does_not_rewrite_string_arguments() -> None:
    from elmos_polyglot_route.models import Function as _Function
    from elmos_polyglot_route.models import Parameter as _Parameter
    from elmos_polyglot_route.validation import _typescript_harness

    function = _Function(
        name="echo",
        parameters=(_Parameter(name="value", type="string"),),
        return_type="string",
        body=(),
    )
    # An earlier revision templated the literal name `calculate` and then
    # string-replaced it, so any occurrence of "calculate" inside a case's own
    # data was rewritten too.
    harness = _typescript_harness(function, [{"args": ["calculate"], "expected": "calculate"}])
    assert 'echo("calculate")' in harness
    assert '"echo"' not in harness


def test_java_harness_compares_strings_by_value() -> None:
    from elmos_polyglot_route.models import Function as _Function
    from elmos_polyglot_route.models import Parameter as _Parameter
    from elmos_polyglot_route.validation import _java_harness

    function = _Function(
        name="echo",
        parameters=(_Parameter(name="value", type="string"),),
        return_type="string",
        body=(),
    )
    harness = _java_harness(function, [{"args": ["a"], "expected": "a"}])
    assert "java.util.Objects.equals" in harness
