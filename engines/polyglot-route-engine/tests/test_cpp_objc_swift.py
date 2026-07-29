"""C++, Objective-C and Swift: canonical type and operator correspondence.

The three added languages differ from the original four in exactly the places
this file pins:

* C++ maps the canonical integer to `std::int64_t` and needs `<cstdint>` /
  `<string>`; `/`, `%` and `==` already mean what the canonical operators
  mean, so nothing is rewritten.
* Objective-C's `NSString *` is a **pointer**: `==` compares addresses and
  there is no `+`, so both are rewritten to message sends in the emitter and
  a source-level `==` on NSString is refused by the analyzer.
* Swift takes no statement terminator, labels parameters with `_` to keep
  call sites positional, and spells a unicode escape `\\u{XXXX}`.

The C++ cases are compiled and executed here; Objective-C is parsed by the
real clang here but needs Foundation (macOS) to link, and Swift needs a Swift
toolchain, so those two are asserted at the emitted-source level.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError, SemanticIR

CLANG = shutil.which("clang")
CLANGXX = shutil.which("clang++")


def _ir(*functions: dict[str, Any]) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Fixture.java",
            "analyzer": "test",
            "analyzer_version": "0",
            "functions": list(functions),
            "diagnostics": [],
        }
    )


def _name(value: str) -> dict[str, Any]:
    return {"kind": "name", "value": value}


def _binary(operator: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def _function(
    name: str, parameters: list[tuple[str, str]], return_type: str, expression: dict[str, Any]
) -> dict[str, Any]:
    return {
        "name": name,
        "parameters": [{"name": n, "type": t} for n, t in parameters],
        "return_type": return_type,
        "body": [{"kind": "return", "expression": expression}],
    }


DIVIDE = _function(
    "divide", [("a", "integer"), ("b", "integer")], "integer", _binary("/", _name("a"), _name("b"))
)
REMAINDER = _function(
    "rem", [("a", "integer"), ("b", "integer")], "integer", _binary("%", _name("a"), _name("b"))
)
STRING_EQUALS = _function(
    "same", [("a", "string"), ("b", "string")], "boolean", _binary("==", _name("a"), _name("b"))
)
STRING_CONCAT = _function(
    "join", [("a", "string"), ("b", "string")], "string", _binary("+", _name("a"), _name("b"))
)


# --------------------------------------------------------------------------
# Type spelling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("cpp", "std::int64_t divide(std::int64_t a, std::int64_t b)"),
        ("objc", "long long divide(long long a, long long b)"),
        ("swift", "func divide(_ a: Int, _ b: Int) -> Int"),
    ],
)
def test_integer_signature(language: str, expected: str) -> None:
    assert expected in emit(_ir(DIVIDE), language).content


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("cpp", "bool same(std::string a, std::string b)"),
        ("objc", "BOOL same(NSString *a, NSString *b)"),
        ("swift", "func same(_ a: String, _ b: String) -> Bool"),
    ],
)
def test_string_and_boolean_signature(language: str, expected: str) -> None:
    assert expected in emit(_ir(STRING_EQUALS), language).content


def test_number_maps_to_double_everywhere() -> None:
    function = _function(
        "ratio", [("a", "number"), ("b", "number")], "number", _binary("/", _name("a"), _name("b"))
    )
    assert "double ratio(double a, double b)" in emit(_ir(function), "cpp").content
    assert "double ratio(double a, double b)" in emit(_ir(function), "objc").content
    assert "func ratio(_ a: Double, _ b: Double) -> Double" in emit(_ir(function), "swift").content


def test_file_names_and_required_headers() -> None:
    cpp = emit(_ir(STRING_EQUALS), "cpp")
    assert cpp.relative_path == "migrated.cpp"
    assert cpp.content.startswith("#include <cstdint>\n#include <string>\n")
    objc = emit(_ir(STRING_EQUALS), "objc")
    assert objc.relative_path == "migrated.m"
    assert objc.content.startswith("#import <Foundation/Foundation.h>\n")
    swift = emit(_ir(STRING_EQUALS), "swift")
    assert swift.relative_path == "migrated.swift"
    assert swift.content.startswith("func ")


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["cpp", "objc", "swift"])
def test_integer_division_and_remainder_need_no_rewrite(language: str) -> None:
    # All three truncate toward zero, like Java/C#/TypeScript and unlike
    # Python -- so the canonical operators map straight through.
    assert "(a / b)" in emit(_ir(DIVIDE), language).content
    assert "(a % b)" in emit(_ir(REMAINDER), language).content


def test_objc_string_equality_becomes_a_value_comparison() -> None:
    content = emit(_ir(STRING_EQUALS), "objc").content
    assert "[a isEqualToString:b]" in content
    assert "a == b" not in content


def test_objc_string_inequality_negates_the_value_comparison() -> None:
    function = _function(
        "differs", [("a", "string"), ("b", "string")], "boolean", _binary("!=", _name("a"), _name("b"))
    )
    assert "(![a isEqualToString:b])" in emit(_ir(function), "objc").content


def test_objc_string_concatenation_becomes_a_message_send() -> None:
    # NSString has no `+` operator at all.
    assert "[a stringByAppendingString:b]" in emit(_ir(STRING_CONCAT), "objc").content


@pytest.mark.parametrize("language", ["cpp", "swift"])
def test_string_equality_and_concatenation_are_native(language: str) -> None:
    assert "(a == b)" in emit(_ir(STRING_EQUALS), language).content
    assert "(a + b)" in emit(_ir(STRING_CONCAT), language).content


# --------------------------------------------------------------------------
# Literals
# --------------------------------------------------------------------------


def _constant(value: Any, return_type: str) -> SemanticIR:
    return _ir(_function("value", [], return_type, {"kind": "literal", "value": value}))


@pytest.mark.parametrize("language", ["cpp", "objc"])
def test_integer_literal_beyond_int32_gets_the_long_long_suffix(language: str) -> None:
    assert "return 9007199254740993LL;" in emit(_constant(9007199254740993, "integer"), language).content
    assert "return 2147483647;" in emit(_constant(2147483647, "integer"), language).content


def test_swift_integer_literal_needs_no_suffix() -> None:
    # Swift's Int is 64-bit on every supported platform.
    assert "return 9007199254740993" in emit(_constant(9007199254740993, "integer"), "swift").content


@pytest.mark.parametrize("language", ["cpp", "objc", "swift"])
def test_integer_literal_beyond_int64_still_fails_closed(language: str) -> None:
    with pytest.raises(RouteError, match="INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE"):
        emit(_constant(2**63, "integer"), language)


def test_boolean_literals_use_each_language_spelling() -> None:
    assert "return true;" in emit(_constant(True, "boolean"), "cpp").content
    assert "return YES;" in emit(_constant(True, "boolean"), "objc").content
    assert "return false" in emit(_constant(False, "boolean"), "swift").content


def test_string_literals_use_each_language_spelling() -> None:
    assert 'return "hi";' in emit(_constant("hi", "string"), "cpp").content
    assert 'return @"hi";' in emit(_constant("hi", "string"), "objc").content
    assert 'return "hi"' in emit(_constant("hi", "string"), "swift").content


def test_swift_rewrites_json_unicode_escapes() -> None:
    # JSON spells a control character ``; Swift spells it `\u{0007}`.
    assert "\\u{0007}" in emit(_constant("\x07", "string"), "swift").content


def test_swift_statements_carry_no_terminator() -> None:
    content = emit(_ir(DIVIDE), "swift").content
    assert "return (a / b)\n" in content
    assert ";" not in content


# --------------------------------------------------------------------------
# Lifting *from* C++ and Objective-C, using clang's own AST.
# --------------------------------------------------------------------------


requires_clang = pytest.mark.skipif(CLANG is None, reason="clang is not installed")


def _analyze(tmp_path: Path, suffix: str, language: str, source: str, function: str) -> SemanticIR:
    from elmos_polyglot_route.clang_analyzer import analyze_clang

    path = tmp_path / f"source{suffix}"
    path.write_text(source, encoding="utf-8")
    executable = CLANGXX if language == "cpp" else CLANG
    assert executable is not None
    return analyze_clang(path, language, function, executable, "test")


_OBJC_PRELUDE = (
    "typedef signed char BOOL;\n"
    "#define YES ((BOOL)1)\n"
    "#define NO ((BOOL)0)\n"
    "@interface NSString\n"
    "- (BOOL)isEqualToString:(NSString *)other;\n"
    "- (NSString *)stringByAppendingString:(NSString *)other;\n"
    "@end\n"
)


@requires_clang
def test_cpp_source_lifts_scalars_and_control_flow(tmp_path: Path) -> None:
    semantic = _analyze(
        tmp_path,
        ".cpp",
        "cpp",
        "#include <cstdint>\n"
        "std::int64_t calculate(std::int64_t subtotal, std::int64_t tax) {\n"
        "    if (subtotal < 0) { return 0; }\n"
        "    return subtotal + tax;\n"
        "}\n",
        "calculate",
    )
    function = semantic.functions[0]
    assert [(p.name, p.type) for p in function.parameters] == [
        ("subtotal", "integer"),
        ("tax", "integer"),
    ]
    assert function.return_type == "integer"
    assert [statement.kind for statement in function.body] == ["if", "return"]
    assert "public static long calculate(long subtotal, long tax)" in emit(semantic, "java").content


@requires_clang
def test_cpp_const_reference_string_parameters_lift_as_string(tmp_path: Path) -> None:
    # `const std::string &` is how C++ passes a string by value to a pure
    # function; the canonical model has no reference notion, so the qualifiers
    # are stripped rather than the parameter being refused.
    semantic = _analyze(
        tmp_path,
        ".cpp",
        "cpp",
        "#include <string>\nbool same(const std::string &a, const std::string &b) { return a == b; }\n",
        "same",
    )
    assert [p.type for p in semantic.functions[0].parameters] == ["string", "string"]
    assert "[a isEqualToString:b]" in emit(semantic, "objc").content


@requires_clang
def test_cpp_float_parameter_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RouteError, match="FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET"):
        _analyze(tmp_path, ".cpp", "cpp", "float half(float v) { return v; }\n", "half")


@requires_clang
def test_objc_source_lifts_message_sends_as_string_operations(tmp_path: Path) -> None:
    semantic = _analyze(
        tmp_path,
        ".m",
        "objc",
        _OBJC_PRELUDE + "BOOL same(NSString *a, NSString *b) { return [a isEqualToString:b]; }\n",
        "same",
    )
    assert [p.type for p in semantic.functions[0].parameters] == ["string", "string"]
    assert "(a.equals(b))" in emit(semantic, "java").content
    assert "(a == b)" in emit(semantic, "swift").content


@requires_clang
def test_objc_string_pointer_comparison_fails_closed(tmp_path: Path) -> None:
    # `a == b` on NSString * compares addresses, so two equal strings answer
    # NO. Lifting it as canonical equality would change the meaning on every
    # other target.
    with pytest.raises(RouteError, match="OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET"):
        _analyze(
            tmp_path,
            ".m",
            "objc",
            _OBJC_PRELUDE + "BOOL same(NSString *a, NSString *b) { return a == b; }\n",
            "same",
        )


@requires_clang
def test_a_source_that_does_not_compile_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RouteError, match="SOURCE_DIAGNOSTICS_BLOCK_ANALYSIS"):
        _analyze(tmp_path, ".cpp", "cpp", "int broken(int a) { return a +; }\n", "broken")


# --------------------------------------------------------------------------
# Executed behaviour: the emitted C++ must agree with Java and Python on the
# sign cases that separate truncating from flooring arithmetic.
# --------------------------------------------------------------------------


@pytest.mark.skipif(CLANGXX is None, reason="clang++ is not installed")
@pytest.mark.parametrize(
    ("a", "b", "quotient", "remainder"),
    [(7, 2, 3, 1), (-7, 2, -3, -1), (7, -2, -3, 1), (-7, -2, 3, -1)],
)
def test_emitted_cpp_truncates_like_java(
    tmp_path: Path, a: int, b: int, quotient: int, remainder: int
) -> None:
    source = emit(_ir(DIVIDE, REMAINDER), "cpp").content
    harness = (
        f"{source}\n#include <cstdio>\n"
        "int main() {\n"
        f"    if (divide({a}, {b}) != {quotient}) return 1;\n"
        f"    if (rem({a}, {b}) != {remainder}) return 2;\n"
        "    return 0;\n"
        "}\n"
    )
    path = tmp_path / "harness.cpp"
    path.write_text(harness, encoding="utf-8")
    binary = tmp_path / "harness"
    assert CLANGXX is not None
    compiled = subprocess.run(
        [CLANGXX, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-o", str(binary), str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert compiled.returncode == 0, compiled.stderr
    assert subprocess.run([str(binary)], check=False, timeout=60).returncode == 0
