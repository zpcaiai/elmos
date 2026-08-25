"""Kotlin target-side contract, asserted without a Kotlin toolchain.

Everything here is pure Python: the emitter, the identifier plan and the
behaviour-harness generator all produce *text*, and the properties that matter
about that text are the ones a compiler would only catch by failing to build --
long after the evidence for a route was supposed to be trustworthy.  So they
are asserted directly.

The three Kotlin facts that make this worth a file of its own, rather than a
few lines appended to the shared target tests:

* An unsuffixed integer literal is an `Int`, so it overflows at 2^31 inside a
  matrix whose canonical integer is 64-bit.  Every emitted integer needs `L`.
* `-9223372036854775808L` does not compile.  Kotlin has no negative literal:
  that is unary minus applied to a literal one past `Long.MAX_VALUE`.
* A double-quoted string interpolates `$name`, so an un-escaped `$` in a string
  literal is either a compile error or -- if the name happens to exist -- a
  silently different string.

Each of those is a wrong answer rather than a crash if the emitter gets it
wrong, which is exactly the class of bug this suite exists to refuse.
"""

from __future__ import annotations

import pytest

from elmos_polyglot_route import identifier_hygiene as hygiene
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers
from elmos_polyglot_route.models import (
    PENDING_ANALYZER_LANGUAGES,
    REPOSITORY_SURFACE_LANGUAGES,
    RouteError,
    SemanticIR,
    is_routed_pair,
)
from elmos_polyglot_route.validation import (
    _KOTLIN_HARNESS_JVM_NAME,
    _kotlin_harness,
    _kotlin_literal,
    _kotlin_package,
)

INTEGER_MIN = -(2**63)
INTEGER_MAX = 2**63 - 1


def _ir(
    name: str,
    parameters: list[dict[str, str]],
    return_type: str,
    body: list[dict[str, object]],
) -> SemanticIR:
    # `python` rather than `kotlin` as the source language: kotlin is still a
    # pending-analyzer language, so a kotlin-sourced SemanticIR is refused by
    # construction.  The target side does not care where the IR came from.
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "subject.py",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": name,
                    "parameters": parameters,
                    "return_type": return_type,
                    "body": body,
                }
            ],
            "diagnostics": [],
        }
    )


def _identity(name: str, value_type: str) -> SemanticIR:
    return _ir(
        name,
        [{"name": "value", "type": value_type}],
        value_type,
        [{"kind": "return", "expression": {"kind": "name", "value": "value"}}],
    )


def _emit(ir: SemanticIR) -> str:
    return emit(ir, "kotlin", identifier_plan=plan_identifiers(ir, "kotlin")).content


# --------------------------------------------------------------- emitted source


def test_kotlin_is_declared_in_the_matrix_but_not_yet_liftable() -> None:
    """The state this whole file is written against, asserted up front.

    If kotlin ever leaves PENDING_ANALYZER_LANGUAGES, the `_ir` helper's comment
    stops being true and this suite should be revisited rather than silently
    testing something else.
    """
    assert "kotlin" in PENDING_ANALYZER_LANGUAGES
    assert "kotlin" not in REPOSITORY_SURFACE_LANGUAGES
    assert is_routed_pair("kotlin", "python")
    assert is_routed_pair("python", "kotlin")


def test_emitted_signature_and_types_are_the_sixty_four_bit_spellings() -> None:
    source = _emit(
        _ir(
            "calculate",
            [{"name": "subtotal", "type": "integer"}, {"name": "tax", "type": "integer"}],
            "integer",
            [
                {
                    "kind": "return",
                    "expression": {
                        "kind": "binary",
                        "operator": "+",
                        "left": {"kind": "name", "value": "subtotal"},
                        "right": {"kind": "name", "value": "tax"},
                    },
                }
            ],
        )
    )
    assert "fun calculate(subtotal: Long, tax: Long): Long {" in source
    # `Int` must not appear as a declared type anywhere: it is the one spelling
    # that compiles, runs, and answers differently from every other target.
    assert ": Int" not in source
    assert ": Float" not in source
    # No package declaration -- the placer adds the one that matches where the
    # file lands, which is what keeps two `migrated.kt` units from colliding.
    assert not source.lstrip().startswith("package ")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0L"),
        (1, "1L"),
        (-1, "-1L"),
        # `9223372036854775807L` is a legal Long literal, so the maximum needs
        # no constant.  The minimum does: Kotlin has no negative literals, and
        # `-9223372036854775808L` is unary minus applied to a magnitude one past
        # Long's range, which the compiler rejects outright.  The asymmetry is
        # the point -- an earlier draft of this test demanded `Long.MAX_VALUE`
        # too and was simply wrong about the language.
        (INTEGER_MAX, "9223372036854775807L"),
        (INTEGER_MIN, "Long.MIN_VALUE"),
    ],
)
def test_every_emitted_integer_literal_is_a_long(value: int, expected: str) -> None:
    source = _emit(
        _ir(
            "constant",
            [{"name": "value", "type": "integer"}],
            "integer",
            [{"kind": "return", "expression": {"kind": "literal", "value": value}}],
        )
    )
    assert f"return {expected}" in source


def test_integer_arithmetic_never_reaches_a_bare_operator() -> None:
    """Kotlin's `Long` wraps on overflow exactly as Java's does.

    Emitting a bare `a + b` would answer -2^63 where the canonical rule says
    "error", so the presence of a checked call is the whole compensation.
    Which call it is follows Java: `java.lang.Math` is default-imported on
    Kotlin/JVM and its `addExact` family already throws, so `+`, `-` and `*`
    need no helper of ours.  Only `/` and `%` do, because `Math` has no
    checked division.
    """
    source = _emit(
        _ir(
            "add",
            [{"name": "left", "type": "integer"}, {"name": "right", "type": "integer"}],
            "integer",
            [
                {
                    "kind": "return",
                    "expression": {
                        "kind": "binary",
                        "operator": "+",
                        "left": {"kind": "name", "value": "left"},
                        "right": {"kind": "name", "value": "right"},
                    },
                }
            ],
        )
    )
    assert "Math.addExact(left, right)" in source
    # Nothing of ours is emitted for `+`, so no unused private helper is left
    # behind either.
    assert "elmosChecked" not in source


def test_float_division_guards_the_divisor() -> None:
    source = _emit(
        _ir(
            "ratio",
            [{"name": "left", "type": "number"}, {"name": "right", "type": "number"}],
            "number",
            [
                {
                    "kind": "return",
                    "expression": {
                        "kind": "binary",
                        "operator": "/",
                        "left": {"kind": "name", "value": "left"},
                        "right": {"kind": "name", "value": "right"},
                    },
                }
            ],
        )
    )
    # Without the guard Kotlin answers Infinity, which no other target does.
    assert "elmosNonZero(right)" in source
    assert "private fun elmosNonZero(value: Double): Double {" in source
    assert "throw ArithmeticException" in source
    # The emitted helper shares one top-level namespace with every migrated
    # function in the file, so the identifier policy has to reserve its name or
    # a source function called `elmosNonZero` becomes a redeclaration error.
    assert "elmosNonZero" in hygiene._FORBIDDEN["kotlin"]


def test_integer_to_number_widening_is_explicit() -> None:
    """Kotlin has no implicit numeric widening; a bare `Long` return would not compile.

    This one was right the first time and the emitter was not: `return v` where
    `v: Long` and the return type is `Double` is a type error, and kotlin was
    absent from the return-site widening that rust and swift already had. With
    no pinned kotlinc the emitted file is never built, so an assertion on the
    text is the only thing that can see it.
    """
    source = _emit(
        _ir(
            "widen",
            [{"name": "value", "type": "integer"}],
            "number",
            [{"kind": "return", "expression": {"kind": "name", "value": "value"}}],
        )
    )
    assert ".toDouble()" in source
    # Parenthesised: `.` binds tighter than unary minus, so an unwrapped
    # `-5L.toDouble()` would parse as `-(5L.toDouble())`.
    assert "return (" in source and ").toDouble()" in source


def test_a_dollar_sign_in_a_string_literal_is_escaped() -> None:
    """The failure this exists to catch is silent, not loud.

    `"$value"` inside a function that happens to have a `value` parameter
    compiles and returns the parameter's contents instead of the literal.
    """
    source = _emit(
        _ir(
            "label",
            [{"name": "value", "type": "string"}],
            "string",
            [{"kind": "return", "expression": {"kind": "literal", "value": "$value and $0"}}],
        )
    )
    assert r"\$value" in source
    assert '"$value' not in source


# ------------------------------------------------------------------- harness


def test_harness_declares_its_jvm_class_name_instead_of_deriving_it() -> None:
    """Kotlin names a file class after the file with only the first letter
    capitalised: `route_harness.kt` becomes `Route_harnessKt`, NOT
    `RouteHarnessKt`.  Both dispatch sites run the declared name, so the
    annotation has to be present or the harness fails at run time with
    "could not find or load main class"."""
    harness = _kotlin_harness(
        _identity("label", "string").functions[0],
        [{"args": ["x"], "expected": "x"}],
        "migrated.kt",
    )
    assert f'@file:JvmName("{_KOTLIN_HARNESS_JVM_NAME}")' in harness
    assert "Route_harnessKt" not in harness
    assert "fun main() {" in harness


@pytest.mark.parametrize(
    ("value_type", "encoding"),
    [("integer", "i64-dec"), ("number", "fp64-hex"), ("boolean", "bool"), ("string", "hex-utf8")],
)
def test_harness_emits_the_declared_observation_encoding(value_type: str, encoding: str) -> None:
    case_value: object = {"integer": 1, "number": 0.5, "boolean": True, "string": "x"}[value_type]
    harness = _kotlin_harness(
        _identity("subject", value_type).functions[0],
        [{"args": [case_value], "expected": case_value}],
        "migrated.kt",
    )
    assert f'\\t{encoding}\\t' in harness


def test_harness_compares_float_results_bit_exactly() -> None:
    """`==` on Double collapses -0.0 with 0.0 and makes every NaN unequal.

    Neither is the question the evidence is asking, so the harness compares raw
    bits -- and `toRawBits`, not `toBits`, because the latter canonicalises NaN
    payloads away.
    """
    harness = _kotlin_harness(
        _identity("subject", "number").functions[0],
        [{"args": [0.5], "expected": 0.5}],
        "migrated.kt",
    )
    assert "toRawBits()" in harness
    assert "toBits()" not in harness.replace("toRawBits()", "")


def test_harness_builds_strings_from_utf8_bytes() -> None:
    """A quoted Kotlin string would interpolate `$`; bytes cannot."""
    harness = _kotlin_harness(
        _identity("subject", "string").functions[0],
        [{"args": ["héllo"], "expected": "héllo"}],
        "migrated.kt",
    )
    assert "byteArrayOf(" in harness
    assert "Charsets.UTF_8" in harness
    assert "0xc3.toByte()" in harness


def test_harness_only_emits_the_helper_its_return_type_reaches() -> None:
    """The dispatch sites compile with `-Werror`, and an unused private
    top-level function is a Kotlin warning -- so emitting the whole helper set
    unconditionally would fail the build rather than merely be untidy."""
    integer_harness = _kotlin_harness(
        _identity("subject", "integer").functions[0],
        [{"args": [1], "expected": 1}],
        "migrated.kt",
    )
    assert "elmosHarnessFP64" not in integer_harness
    assert "elmosHarnessHexUTF8" not in integer_harness


# ------------------------------------------------------------------- literals


@pytest.mark.parametrize(
    ("value", "value_type", "expected"),
    [
        (0, "integer", "0L"),
        (INTEGER_MAX, "integer", "Long.MAX_VALUE"),
        (INTEGER_MIN, "integer", "Long.MIN_VALUE"),
        (True, "boolean", "true"),
        (False, "boolean", "false"),
    ],
)
def test_case_literals_are_rendered_by_canonical_type(
    value: object, value_type: str, expected: str
) -> None:
    assert _kotlin_literal(value, value_type) == expected


def test_an_integer_valued_case_for_a_number_parameter_renders_as_a_double() -> None:
    """JSON has one number type; Kotlin has no implicit widening.

    Rendering by the Python value's type instead of the declared canonical type
    would emit `3L` for a `Double` parameter, which does not compile.
    """
    assert _kotlin_literal(3, "number") == "3.0"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("package pricing\n\nfun f() {}\n", "pricing"),
        ("package com.example.app\n", "com.example.app"),
        ("fun f() {}\n", ""),
        ("// package commented\nfun f() {}\n", ""),
    ],
)
def test_package_extraction(text: str, expected: str) -> None:
    assert _kotlin_package(text) == expected


def test_a_kotlin_sourced_semantic_ir_is_still_refused() -> None:
    with pytest.raises(RouteError, match=r"^SOURCE_ANALYZER_NOT_IMPLEMENTED:kotlin$"):
        SemanticIR.from_mapping(
            {
                "schema_version": "1.0.0",
                "source_language": "kotlin",
                "source_file": "subject.kt",
                "analyzer": "test",
                "analyzer_version": "1",
                "functions": [
                    {
                        "name": "identity",
                        "parameters": [{"name": "value", "type": "integer"}],
                        "return_type": "integer",
                        "body": [
                            {"kind": "return", "expression": {"kind": "name", "value": "value"}}
                        ],
                    }
                ],
                "diagnostics": [],
            }
        )
