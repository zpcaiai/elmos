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

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import (
    alpha_normalize_target,
    plan_identifiers,
    target_ir_view,
)
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


DIVIDE = _function("divide", [("a", "integer"), ("b", "integer")], "integer", _binary("/", _name("a"), _name("b")))
REMAINDER = _function("rem", [("a", "integer"), ("b", "integer")], "integer", _binary("%", _name("a"), _name("b")))
STRING_EQUALS = _function("same", [("a", "string"), ("b", "string")], "boolean", _binary("==", _name("a"), _name("b")))
STRING_CONCAT = _function("join", [("a", "string"), ("b", "string")], "string", _binary("+", _name("a"), _name("b")))


# --------------------------------------------------------------------------
# Type spelling
# --------------------------------------------------------------------------


def _emitted(ir: SemanticIR, language: str) -> tuple[str, Any]:
    """Emit, and return a rewriter from source spellings to the planned ones.

    Identifier hygiene refuses the source spelling outright for these three
    targets -- function names in all of cpp, objc and swift, parameter names in
    cpp and objc -- because a C-family global symbol namespace is open to
    collision and a preprocessor can rewrite any identifier. An assertion
    written against the source names therefore ends up testing that policy
    rather than the lowering it is named for. Rewriting the expected spelling
    through the plan keeps each assertion about its own subject, and keeps it
    true whatever the plan decides, without pinning a digest into the test.

    Parameter names are scoped per function, so for an IR carrying more than one
    function only the last function's parameters survive in the map. Callers
    passing several functions should rewrite function names only.
    """
    plan = plan_identifiers(ir, language)
    renames: dict[str, str] = {}
    for source_function, target_function in zip(
        ir.functions, target_ir_view(ir, plan).functions, strict=True
    ):
        renames[source_function.name] = target_function.name
        for source, target in zip(
            source_function.parameters, target_function.parameters, strict=True
        ):
            renames[source.name] = target.name

    def planned(spelling: str) -> str:
        for source, target in renames.items():
            spelling = re.sub(rf"\b{re.escape(source)}\b", target, spelling)
        return spelling

    return emit(ir, language, identifier_plan=plan).content, planned


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("cpp", "std::int64_t divide(std::int64_t a, std::int64_t b)"),
        ("objc", "long long divide(long long a, long long b)"),
        ("swift", "func divide(_ a: Int64, _ b: Int64) -> Int64"),
    ],
)
def test_integer_signature(language: str, expected: str) -> None:
    content, planned = _emitted(_ir(DIVIDE), language)
    assert planned(expected) in content


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("cpp", "bool same(std::string a, std::string b)"),
        ("objc", "BOOL same(NSString *a, NSString *b)"),
        ("swift", "func same(_ a: String, _ b: String) -> Bool"),
    ],
)
def test_string_and_boolean_signature(language: str, expected: str) -> None:
    content, planned = _emitted(_ir(STRING_EQUALS), language)
    assert planned(expected) in content


def test_number_maps_to_double_everywhere() -> None:
    function = _function("ratio", [("a", "number"), ("b", "number")], "number", _binary("/", _name("a"), _name("b")))
    for language, expected in (
        ("cpp", "double ratio(double a, double b)"),
        ("objc", "double ratio(double a, double b)"),
        ("swift", "func ratio(_ a: Double, _ b: Double) -> Double"),
    ):
        content, planned = _emitted(_ir(function), language)
        assert planned(expected) in content


def test_file_names_and_required_headers() -> None:
    cpp = emit(_ir(STRING_EQUALS), "cpp")
    assert cpp.relative_path == "migrated.cpp"
    assert cpp.content.startswith("#include <cstdint>\n#include <stdexcept>\n#include <string>\n")
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
def test_integer_division_and_remainder_are_checked(language: str) -> None:
    # All three truncate toward zero like Java/C#/TypeScript, so the *rounding*
    # maps straight through -- but signed overflow and division by zero are
    # undefined behaviour in C and C++, so R1/R2 have to be spelled out.
    divide, divide_planned = _emitted(_ir(DIVIDE), language)
    remainder, remainder_planned = _emitted(_ir(REMAINDER), language)
    if language == "cpp":
        assert divide_planned("return elmos_checked_div(a, b);") in divide
        assert remainder_planned("return elmos_checked_mod(a, b);") in remainder
    elif language == "objc":
        assert divide_planned("return ElmosCheckedDiv(a, b);") in divide
        assert remainder_planned("return ElmosCheckedMod(a, b);") in remainder
    else:
        # Swift is the one target of the three that traps on both by itself:
        # Int64 division by zero and Int64.min / -1 are runtime errors already.
        assert divide_planned("return (a / b)") in divide
        assert remainder_planned("return (a % b)") in remainder


def test_objc_string_equality_becomes_a_value_comparison() -> None:
    content, planned = _emitted(_ir(STRING_EQUALS), "objc")
    assert planned("[a isEqualToString:b]") in content
    assert planned("a == b") not in content


def test_objc_string_inequality_negates_the_value_comparison() -> None:
    function = _function(
        "differs", [("a", "string"), ("b", "string")], "boolean", _binary("!=", _name("a"), _name("b"))
    )
    content, planned = _emitted(_ir(function), "objc")
    assert planned("(![a isEqualToString:b])") in content


def test_objc_string_concatenation_becomes_a_message_send() -> None:
    # NSString has no `+` operator at all.
    content, planned = _emitted(_ir(STRING_CONCAT), "objc")
    assert planned("[a stringByAppendingString:b]") in content


@pytest.mark.parametrize("language", ["cpp", "swift"])
def test_string_equality_and_concatenation_are_native(language: str) -> None:
    equals, equals_planned = _emitted(_ir(STRING_EQUALS), language)
    concat, concat_planned = _emitted(_ir(STRING_CONCAT), language)
    assert equals_planned("(a == b)") in equals
    assert concat_planned("(a + b)") in concat


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
    # Int64 makes the exact width part of the emitted source contract.
    assert "return Int64(9007199254740993)" in emit(_constant(9007199254740993, "integer"), "swift").content


def test_swift_widens_integer_operands_in_number_expressions() -> None:
    compared = _function(
        "is_negative",
        [("value", "number")],
        "boolean",
        _binary("<", _name("value"), {"kind": "literal", "value": 0}),
    )
    assert "(value < Double(Int64(0)))" in emit(_ir(compared), "swift").content


def test_swift_widens_integer_return_to_number() -> None:
    assert "return Double(Int64(0))" in emit(_constant(0, "number"), "swift").content


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
    content, planned = _emitted(semantic, "java")
    assert planned("public static long calculate(long subtotal, long tax)") in content


@requires_clang
def test_cpp_ast_filter_selects_the_exact_name_from_multiple_json_documents(
    tmp_path: Path,
) -> None:
    semantic = _analyze(
        tmp_path,
        ".cpp",
        "cpp",
        "#include <cstdint>\n"
        "std::int64_t calculate(std::int64_t value) { return value; }\n"
        "std::int64_t calculateTotal(std::int64_t value) { return value + 1; }\n",
        "calculate",
    )
    assert [function.name for function in semantic.functions] == ["calculate"]


@requires_clang
def test_cpp_inventory_precompiles_system_headers_without_losing_main_file_closure(
    tmp_path: Path,
) -> None:
    from elmos_polyglot_route.clang_analyzer import inventory_clang_module

    source = tmp_path / "bounded_inventory.cpp"
    source.write_text(
        "#include <cstdint>\n"
        "#include <stdexcept>\n"
        "#include <string>\n\n"
        "using Amount = std::int64_t;\n"
        "static Amount checked_add(Amount left, Amount right) { return left + right; }\n"
        "bool same(const std::string &left, const std::string &right) { return left == right; }\n",
        encoding="utf-8",
    )
    assert CLANGXX is not None

    inventory = inventory_clang_module(source, "cpp", CLANGXX, "test")

    assert inventory["enumeration_status"] == "PASSED"
    assert [
        (subject["declaration_kind"], subject["name"])
        for subject in inventory["subjects"]
    ] == [
        ("TypeAliasDecl", "Amount"),
        ("FunctionDecl", "checked_add"),
        ("FunctionDecl", "same"),
    ]
    assert all(
        subject["source_span"]["end_byte"] <= source.stat().st_size
        for subject in inventory["subjects"]
    )


@pytest.mark.skipif(
    sys.platform != "darwin" or CLANG is None,
    reason="Foundation inventory requires Apple clang",
)
def test_objc_inventory_precompiles_foundation_without_losing_main_file_closure(
    tmp_path: Path,
) -> None:
    from elmos_polyglot_route.clang_analyzer import inventory_clang_module

    source = tmp_path / "bounded_inventory.m"
    source.write_text(
        "#import <Foundation/Foundation.h>\n\n"
        "long long calculate(long long left, long long right) { return left + right; }\n"
        "BOOL both(BOOL left, BOOL right) { return left && right; }\n",
        encoding="utf-8",
    )
    assert CLANG is not None

    inventory = inventory_clang_module(source, "objc", CLANG, "test")

    assert inventory["enumeration_status"] == "PASSED"
    assert [subject["name"] for subject in inventory["subjects"]] == ["calculate", "both"]
    assert all(subject["analyzable"] is True for subject in inventory["subjects"])


def test_pch_optimization_accepts_only_exact_emitter_owned_preludes(tmp_path: Path) -> None:
    from elmos_polyglot_route.clang_analyzer import _system_header_prelude

    source = tmp_path / "module.cpp"
    source.write_text(
        "#include <cstdint>\n#include <stdexcept>\n#include <string>\n\nvoid run() {}\n",
        encoding="utf-8",
    )
    assert _system_header_prelude(source, "cpp") is not None

    source.write_text("#include <vector>\n\nvoid run() {}\n", encoding="utf-8")
    assert _system_header_prelude(source, "cpp") is None

    source.write_text(
        "#include <cstdint>\n#include <stdexcept>\n#include <string>\n\n"
        "#include <vector>\nvoid run() {}\n",
        encoding="utf-8",
    )
    assert _system_header_prelude(source, "cpp") is None


def test_pch_inventory_stages_share_one_deadline(tmp_path: Path, monkeypatch) -> None:
    import elmos_polyglot_route.clang_analyzer as clang_analyzer

    source = tmp_path / "module.cpp"
    source.write_text(
        "#include <cstdint>\n#include <stdexcept>\n#include <string>\n\nvoid run() {}\n",
        encoding="utf-8",
    )
    timeouts: list[float] = []
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        timeouts.append(kwargs["timeout"])
        if calls == 2:
            kwargs["stdout_log"].write(b"bounded-pch")
        stdout = '{"kind":"TranslationUnitDecl","inner":[]}' if calls == 3 else ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    ticks = iter((100.0, 101.0, 102.0, 103.0))
    monkeypatch.setattr(clang_analyzer, "run_bounded", fake_run)
    monkeypatch.setattr(clang_analyzer, "_sdk_path", lambda _value: "/sdk")
    monkeypatch.setattr(clang_analyzer.time, "monotonic", lambda: next(ticks))

    tree = clang_analyzer._run_clang(
        "/clang++",
        source,
        "cpp",
        None,
        precompile_system_prelude=True,
    )

    assert tree["kind"] == "TranslationUnitDecl"
    assert timeouts == [599.0, 598.0, 597.0]


def test_pch_consume_failure_is_infrastructure_and_has_stable_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import elmos_polyglot_route.clang_analyzer as clang_analyzer

    source = tmp_path / "module.cpp"
    source.write_text(
        "#include <cstdint>\n#include <stdexcept>\n#include <string>\n\nvoid run() {}\n",
        encoding="utf-8",
    )
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            kwargs["stdout_log"].write(b"bounded-pch")
        if calls == 3:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                f"{command[-1]}: fatal error: malformed or corrupted AST file",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(clang_analyzer, "run_bounded", fake_run)
    monkeypatch.setattr(clang_analyzer, "_sdk_path", lambda _value: "/sdk")

    with pytest.raises(RouteError) as captured:
        clang_analyzer._run_clang(
            "/clang++",
            source,
            "cpp",
            None,
            precompile_system_prelude=True,
        )

    message = str(captured.value)
    assert message.startswith("NATIVE_ANALYZER_PCH_FAILED:/clang++:")
    assert str(source.resolve()) in message
    assert "elmos-clang-env-" not in message


@requires_clang
def test_cpp_ast_filter_preserves_the_missing_symbol_contract(tmp_path: Path) -> None:
    with pytest.raises(RouteError, match="^FUNCTION_NOT_FOUND:missing$"):
        _analyze(
            tmp_path,
            ".cpp",
            "cpp",
            "#include <cstdint>\nstd::int64_t calculate(std::int64_t value) { return value; }\n",
            "missing",
        )


@requires_clang
def test_cpp_ast_filter_rejects_a_namespaced_function_as_top_level(tmp_path: Path) -> None:
    with pytest.raises(RouteError, match="^FUNCTION_NOT_FOUND:calculate$"):
        _analyze(
            tmp_path,
            ".cpp",
            "cpp",
            "#include <cstdint>\n"
            "namespace billing {\n"
            "std::int64_t calculate(std::int64_t value) { return value + 1; }\n"
            "}\n"
            "using billing::calculate;\n",
            "calculate",
        )


@requires_clang
def test_cpp_ast_filter_selects_global_over_same_named_namespace_function(
    tmp_path: Path,
) -> None:
    semantic = _analyze(
        tmp_path,
        ".cpp",
        "cpp",
        "#include <cstdint>\n"
        "std::int64_t calculate(std::int64_t value) { return value; }\n"
        "namespace billing {\n"
        "std::int64_t calculate(std::int64_t value) { return value + 1; }\n"
        "}\n",
        "calculate",
    )
    expression = semantic.functions[0].body[0].expression
    assert expression is not None
    assert expression.kind == "name"
    assert expression.value == "value"


@requires_clang
def test_cpp_ast_filter_rejects_c_linkage_outside_inventory_scope(tmp_path: Path) -> None:
    from elmos_polyglot_route.clang_analyzer import analyze_clang, inventory_clang_module

    source = tmp_path / "source.cpp"
    source.write_text(
        "#include <cstdint>\n"
        'extern "C" {\n'
        "std::int64_t calculate(std::int64_t value) { return value; }\n"
        "}\n",
        encoding="utf-8",
    )
    assert CLANGXX is not None

    inventory = inventory_clang_module(source, "cpp", CLANGXX, "test")
    subject = next(row for row in inventory["subjects"] if row["name"] == "calculate")
    assert subject["analyzable"] is False
    with pytest.raises(RouteError, match="^FUNCTION_NOT_FOUND:calculate$"):
        analyze_clang(source, "cpp", "calculate", CLANGXX, "test")


@requires_clang
def test_cpp_ast_filter_rejects_hidden_friend_outside_inventory_scope(
    tmp_path: Path,
) -> None:
    with pytest.raises(RouteError, match="^FUNCTION_NOT_FOUND:calculate$"):
        _analyze(
            tmp_path,
            ".cpp",
            "cpp",
            "#include <cstdint>\n"
            "struct Billing {\n"
            "friend std::int64_t calculate(std::int64_t value) { return value; }\n"
            "};\n",
            "calculate",
        )


@requires_clang
def test_cpp_ast_filter_rejects_anonymous_namespace_function(tmp_path: Path) -> None:
    with pytest.raises(RouteError, match="^FUNCTION_NOT_FOUND:calculate$"):
        _analyze(
            tmp_path,
            ".cpp",
            "cpp",
            "#include <cstdint>\n"
            "namespace {\n"
            "std::int64_t calculate(std::int64_t value) { return value; }\n"
            "}\n",
            "calculate",
        )


@requires_clang
def test_cpp_linkage_wrapper_preserves_default_cpp_function_semantics(
    tmp_path: Path,
) -> None:
    """Explicit C++ linkage is transparent while its wrapper stays explicit."""

    from elmos_polyglot_route.clang_analyzer import analyze_clang, inventory_clang_module

    source = tmp_path / "source.cpp"
    source.write_text(
        "#include <cstdint>\n"
        'extern "C++" {\n'
        "std::int64_t calculate(std::int64_t value) { return value; }\n"
        "}\n",
        encoding="utf-8",
    )
    assert CLANGXX is not None

    inventory = inventory_clang_module(source, "cpp", CLANGXX, "test")
    semantic = analyze_clang(source, "cpp", "calculate", CLANGXX, "test")

    subject = next(row for row in inventory["subjects"] if row["name"] == "calculate")
    wrapper = next(
        row for row in inventory["subjects"] if row["declaration_kind"] == "LinkageSpecDecl"
    )
    assert subject["analyzable"] is True
    assert wrapper["analyzable"] is False
    assert semantic.functions[0].name == "calculate"


@requires_clang
def test_cpp_file_static_function_matches_inventory_analyzability(tmp_path: Path) -> None:
    from elmos_polyglot_route.clang_analyzer import analyze_clang, inventory_clang_module

    source = tmp_path / "source.cpp"
    source.write_text(
        "#include <cstdint>\n"
        "static std::int64_t calculate(std::int64_t value) { return value; }\n",
        encoding="utf-8",
    )
    assert CLANGXX is not None

    inventory = inventory_clang_module(source, "cpp", CLANGXX, "test")
    semantic = analyze_clang(source, "cpp", "calculate", CLANGXX, "test")

    subject = next(row for row in inventory["subjects"] if row["name"] == "calculate")
    assert subject["analyzable"] is True
    assert subject["signature"]["visibility"] == "internal"
    assert semantic.functions[0].name == "calculate"


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
    content, planned = _emitted(semantic, "objc")
    assert planned("[a isEqualToString:b]") in content


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
def test_objc_true_false_yes_no_literals_and_nested_branches_lift_exactly(
    tmp_path: Path,
) -> None:
    semantic = _analyze(
        tmp_path,
        ".m",
        "objc",
        "#import <Foundation/Foundation.h>\n"
        "BOOL choose(BOOL flag, BOOL objcStyle) {\n"
        "    if (flag) {\n"
        "        if (objcStyle) { return YES; }\n"
        "        return true;\n"
        "    }\n"
        "    if (objcStyle) { return NO; }\n"
        "    return false;\n"
        "}\n",
        "choose",
    )

    values: list[bool] = []

    def visit_statement(statement: Any) -> None:
        if statement.kind == "return":
            assert statement.expression is not None
            assert statement.expression.kind == "literal"
            values.append(statement.expression.value)
            return
        for nested in (*statement.then_body, *statement.else_body):
            visit_statement(nested)

    for statement in semantic.functions[0].body:
        visit_statement(statement)
    assert values == [True, True, False, False]


def _boolean_branch_ir() -> SemanticIR:
    return _ir(
        {
            "name": "choose",
            "parameters": [{"name": "flag", "type": "boolean"}],
            "return_type": "boolean",
            "body": [
                {
                    "kind": "if",
                    "condition": {"kind": "name", "value": "flag"},
                    "then": [
                        {
                            "kind": "return",
                            "expression": {"kind": "literal", "value": True},
                        }
                    ],
                    "else": [
                        {
                            "kind": "return",
                            "expression": {"kind": "literal", "value": False},
                        }
                    ],
                }
            ],
        }
    )


@requires_clang
def test_emitted_objc_boolean_branch_relifts_true_and_false_and_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    from elmos_polyglot_route.native import analyze

    source_ir = _boolean_branch_ir()
    # Relifting has to look for the symbol the emitted file declares -- objc
    # refuses the source spelling for both the function and its parameters --
    # and the recovered IR has to come back through the plan's alpha map before
    # it can be compared with the source. This is the same pairing
    # `engine.migrate` uses to prove emitter compensation.
    plan = plan_identifiers(source_ir, "objc")
    target_view = target_ir_view(source_ir, plan)
    symbol = target_view.functions[0].name
    emitted = emit(source_ir, "objc", identifier_plan=plan)
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    relifted = alpha_normalize_target(
        source_ir, analyze(target, "objc", symbol, emitted_target=True), plan
    )
    assert relifted.functions[0].semantic_mapping() == source_ir.functions[0].semantic_mapping()

    tampered = emitted.content.replace("return NO;", "return 2;", 1)
    assert tampered != emitted.content
    target.write_text(tampered, encoding="utf-8")
    with pytest.raises(RouteError, match="OBJC_BOOLEAN_INTEGER_COERCION_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(target, "objc", symbol, emitted_target=True)


@requires_clang
def test_cpp_true_and_false_literals_in_branches_lift_exactly(tmp_path: Path) -> None:
    semantic = _analyze(
        tmp_path,
        ".cpp",
        "cpp",
        "bool choose(bool flag) { if (flag) { return true; } return false; }\n",
        "choose",
    )
    function = semantic.functions[0]
    assert function.body[0].then_body[0].expression is not None
    assert function.body[0].then_body[0].expression.value is True
    assert function.body[1].expression is not None
    assert function.body[1].expression.value is False


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
def test_emitted_cpp_truncates_like_java(tmp_path: Path, a: int, b: int, quotient: int, remainder: int) -> None:
    source, planned = _emitted(_ir(DIVIDE, REMAINDER), "cpp")
    # cpp gets planned function names, so the harness has to call what the file
    # declares. The arithmetic under test is unaffected by what they are called.
    divide_symbol = planned("divide")
    remainder_symbol = planned("rem")
    harness = (
        f"{source}\n#include <cstdio>\n"
        "int main() {\n"
        f"    if ({divide_symbol}({a}, {b}) != {quotient}) return 1;\n"
        f"    if ({remainder_symbol}({a}, {b}) != {remainder}) return 2;\n"
        "    return 0;\n"
        "}\n"
    )
    path = tmp_path / "harness.cpp"
    path.write_text(harness, encoding="utf-8")
    binary = tmp_path / "harness"
    assert CLANGXX is not None
    compiled = subprocess.run(
        [CLANGXX, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-o", str(binary), str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert compiled.returncode == 0, compiled.stderr
    assert subprocess.run([str(binary)], check=False, timeout=60).returncode == 0


# --------------------------------------------------------------------------
# Swift source analysis. The helper under `native/swift` is a SwiftSyntax
# package built on demand, so these run only where a Swift toolchain and its
# declared pin exist -- everywhere else the route fails closed rather than
# falling back on a text-level parse.
# --------------------------------------------------------------------------


SWIFTC = shutil.which("swiftc")


@pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")
def test_swift_source_lifts_through_the_swiftsyntax_helper(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "pricing.swift"
    source.write_text(
        "func calculate(_ subtotal: Int64, _ tax: Int64) -> Int64 {\n"
        "    if subtotal < 0 {\n"
        "        return 0\n"
        "    }\n"
        "    return subtotal + tax\n"
        "}\n",
        encoding="utf-8",
    )
    semantic = analyze(source, "swift", "calculate")
    function = semantic.functions[0]
    assert [(p.name, p.type) for p in function.parameters] == [
        ("subtotal", "integer"),
        ("tax", "integer"),
    ]
    assert function.return_type == "integer"
    assert [statement.kind for statement in function.body] == ["if", "return"]
    assert semantic.diagnostics == ()
    content, planned = _emitted(semantic, "java")
    assert planned("public static long calculate(long subtotal, long tax)") in content


@pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")
def test_swift_emitted_target_relifts_exact_integer_to_double_widening(
    tmp_path: Path,
) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "widening.swift"
    source.write_text(
        "func widen(_ value: Int64) -> Double { return Double(value) }\n",
        encoding="utf-8",
    )

    semantic = analyze(source, "swift", "widen", emitted_target=True)
    function = semantic.functions[0]
    assert function.return_type == "number"
    assert function.body[0].expression is not None
    assert function.body[0].expression.to_mapping()["kind"] == "name"
    assert function.body[0].expression.to_mapping()["value"] == "value"


@pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")
@pytest.mark.parametrize(
    "declaration",
    [
        "func f(_ value: Double) -> Double { return Double(value) }",
        "func f(_ value: Int64) -> Double { return Double(value, value) }",
        "func f(_ value: Int64) -> Double { return Double(exactly: value) }",
        "func f() -> Double { return Double(1.5) }",
    ],
)
def test_swift_emitted_target_rejects_noncanonical_double_calls(
    tmp_path: Path, declaration: str
) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "invalid-widening.swift"
    source.write_text(declaration + "\n", encoding="utf-8")
    with pytest.raises(RouteError, match="SWIFT_EMITTED_DOUBLE_WIDENING_INVALID"):
        analyze(source, "swift", "f", emitted_target=True)


@pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")
def test_swift_source_does_not_gain_double_call_authority(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "source-widening.swift"
    source.write_text(
        "func widen(_ value: Int64) -> Double { return Double(value) }\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="SWIFT_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "swift", "widen")


@pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")
def test_swift_missing_symbol_preserves_the_native_failure(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "pricing.swift"
    source.write_text(
        "func calculate(_ subtotal: Int64) -> Int64 { return subtotal }\n",
        encoding="utf-8",
    )
    with pytest.raises(
        RouteError,
        match="^FUNCTION_NOT_FOUND:__elmos_missing_function__$",
    ):
        analyze(source, "swift", "__elmos_missing_function__")


@pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")
@pytest.mark.parametrize(
    ("declaration", "reason"),
    [
        ("func f(_ v: Float) -> Float { return v }", "FLOAT_PRECISION"),
        ("func f(_ v: UInt64) -> UInt64 { return v }", "UNSIGNED_TYPE"),
        ("func f(_ v: Int?) -> Int64 { return 0 }", "OPTIONAL_TYPE"),
        ("func f(_ v: Int) -> Int64 { return Int64(v) }", "INTEGER_WIDTH"),
    ],
)
def test_swift_types_outside_the_subset_fail_closed(tmp_path: Path, declaration: str, reason: str) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "unsupported.swift"
    source.write_text(declaration + "\n", encoding="utf-8")
    with pytest.raises(RouteError, match=reason):
        analyze(source, "swift", "f")


def test_swift_is_both_a_source_and_a_target() -> None:
    from elmos_polyglot_route.models import ANALYZABLE_LANGUAGES, SUPPORTED_LANGUAGES

    assert "swift" in SUPPORTED_LANGUAGES
    assert "swift" in ANALYZABLE_LANGUAGES
    routes = [(s, t) for s in ANALYZABLE_LANGUAGES for t in SUPPORTED_LANGUAGES if s != t]
    assert len(routes) == len(ANALYZABLE_LANGUAGES) * (len(SUPPORTED_LANGUAGES) - 1)
