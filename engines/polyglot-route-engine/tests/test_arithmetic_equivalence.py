"""Regression tests for the three equivalence defects rules R1/R2 close.

Each was reproducible from the *same* semantic IR before the fix, and none was
reachable by the route corpora, whose nine cases are all small positive
integers:

1. Associativity was dropped for Rust only. The emitter parenthesised every
   other target and returned `f"{left} {rendered} {right}"` for Rust, so the IR
   for `(a + b) * c` came out as `a + b * c`. `f(1, 2, 3)` answered 9
   everywhere and 7 in Rust -- a wrong value, no diagnostic.

2. Integer overflow was uncompensated. `INT64_MAX + 1` wrapped in Java, C# and
   Go, panicked in a debug Rust build but wrapped in release, returned an exact
   2^63 in Python, and was undefined behaviour in C++/Objective-C.

3. Integer division by zero was uncompensated in TypeScript, where
   `Math.trunc(a / 0)` is `Infinity` and `a % 0` is `NaN`. Float division by
   zero diverged the other way: Python raises where the other eight answer
   IEEE Infinity/NaN.

The differential test at the bottom runs the two targets this process can
execute without a compiler -- Python in-process and TypeScript through Node's
type stripping -- over a boundary corpus, and asserts the one asymmetry the
profile documents: TypeScript may fail where Python succeeds, but only outside
the safe-integer range, and it may never answer a different value.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, target_ir_view
from elmos_polyglot_route.models import ROUTED_LANGUAGES, Language, SemanticIR

INTEGER_MAX = 2**63 - 1
INTEGER_MIN = -(2**63)
SAFE_MAX = 2**53 - 1


def _emitted(ir: SemanticIR, language: Language) -> tuple[str, Any]:
    """Emit, and return a rewriter from source spellings to the planned ones.

    Identifier hygiene refuses the source spelling outright for some targets --
    function names in cpp, objc, java, csharp and swift, parameter names in cpp
    and objc -- because those namespaces are open to collision. An assertion
    written against the source names therefore ends up testing that policy
    instead of the lowering it is named for. Rewriting the expected spelling
    through the plan keeps each assertion about its own subject, and keeps it
    true whatever the plan decides, without pinning a digest into the test.
    """
    plan = plan_identifiers(ir, language)
    source_function = ir.functions[0]
    target_function = target_ir_view(ir, plan).functions[0]
    renames = {source_function.name: target_function.name}
    renames.update(
        {
            source.name: target.name
            for source, target in zip(source_function.parameters, target_function.parameters, strict=True)
        }
    )

    def planned(spelling: str) -> str:
        for source, target in renames.items():
            spelling = re.sub(rf"\b{re.escape(source)}\b", target, spelling)
        return spelling

    return emit(ir, language, identifier_plan=plan).content, planned


ALL_TARGETS: tuple[Language, ...] = ROUTED_LANGUAGES


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


# --------------------------------------------------------------------------
# 1. Associativity -- the Rust-only precedence loss
# --------------------------------------------------------------------------

#: (a + b) * c. Rendered without grouping this reassociates to a + (b * c).
_SUM_TIMES = _function(
    "f",
    [("a", "integer"), ("b", "integer"), ("c", "integer")],
    "integer",
    _binary("*", _binary("+", _name("a"), _name("b")), _name("c")),
)

#: a < (b + c) as an `if` condition, to pin the one position where Rust must
#: *not* be parenthesised: `if (cond)` is an unused_parens error under
#: `rustc -D warnings`, which the route harness compiles with.
_NESTED_CONDITION = {
    "name": "g",
    "parameters": [{"name": n, "type": "integer"} for n in ("a", "b", "c")],
    "return_type": "integer",
    "body": [
        {
            "kind": "if",
            "condition": _binary("<", _name("a"), _binary("+", _name("b"), _name("c"))),
            "then": [{"kind": "return", "expression": {"kind": "literal", "value": 0}}],
            "else": [],
        },
        {"kind": "return", "expression": {"kind": "literal", "value": 1}},
    ],
}


def test_rust_no_longer_drops_grouping_in_a_nested_expression() -> None:
    content = emit(_ir(_SUM_TIMES), "rust").content
    assert "a + b * c" not in content, "the reassociation defect is back"
    # The checked form carries its own grouping, which is what preserves the
    # tree: the multiplication takes the *result* of the addition.
    assert '(a).checked_add(b).expect("ELMOS_INTEGER_OVERFLOW")).checked_mul(c)' in content


def test_rust_keeps_the_outermost_position_unparenthesised() -> None:
    # `-D warnings` makes unused_parens an error, so `if (a < ...)` and
    # `return (a < ...)` must not be emitted for Rust.
    content = emit(_ir(_NESTED_CONDITION), "rust").content
    assert "if a < " in content
    assert "if (" not in content


@pytest.mark.parametrize("language", [t for t in ALL_TARGETS if t != "rust"])
def test_every_other_target_already_grouped_and_still_does(language: Language) -> None:
    content = emit(_ir(_SUM_TIMES), language).content
    ungrouped = "$a + $b * $c" if language == "php" else "a + b * c"
    assert ungrouped not in content


# --------------------------------------------------------------------------
# 2. R1 -- integer overflow is an error
# --------------------------------------------------------------------------

_ADD = _function(
    "add", [("a", "integer"), ("b", "integer")], "integer", _binary("+", _name("a"), _name("b"))
)

_CHECKED_ADD_SPELLING: dict[Language, str] = {
    "java": "Math.addExact(a, b)",
    "csharp": "checked(a + b)",
    "python": "_elmos_checked_add(a, b)",
    "typescript": "_elmosRequireSafeInteger(a + b)",
    "react": "_elmosRequireSafeInteger(a + b)",
    "go": "elmosCheckedAdd(a, b)",
    "rust": '(a).checked_add(b).expect("ELMOS_INTEGER_OVERFLOW")',
    "swift": "(a + b)",  # Int arithmetic traps on overflow by default
    "cpp": "elmos_checked_add(a, b)",
    "objc": "ElmosCheckedAdd(a, b)",
    "php": "elmos_checked_add($a, $b)",
    "kotlin": "Math.addExact(a, b)",
    "flutter": "_elmosCheckedAdd(a, b)",
}


@pytest.mark.parametrize("language", ALL_TARGETS)
def test_integer_addition_is_checked_in_every_target(language: Language) -> None:
    content, planned = _emitted(_ir(_ADD), language)
    assert planned(_CHECKED_ADD_SPELLING[language]) in content


def test_python_addition_raises_instead_of_growing_past_the_canonical_range() -> None:
    # The defect: Python's arbitrary precision returned an exact 2^63, a value
    # no other target can hold, and reported success.
    add = _load_python(emit(_ir(_ADD), "python").content, "add")
    assert add(INTEGER_MAX - 1, 1) == INTEGER_MAX
    with pytest.raises(OverflowError, match="ELMOS_INTEGER_OVERFLOW"):
        add(INTEGER_MAX, 1)
    with pytest.raises(OverflowError, match="ELMOS_INTEGER_OVERFLOW"):
        add(INTEGER_MIN, -1)


# --------------------------------------------------------------------------
# 3. R2 -- division or remainder by zero is an error
# --------------------------------------------------------------------------

_DIVIDE = _function(
    "divide", [("a", "integer"), ("b", "integer")], "integer", _binary("/", _name("a"), _name("b"))
)
_REMAINDER = _function(
    "rem", [("a", "integer"), ("b", "integer")], "integer", _binary("%", _name("a"), _name("b"))
)
_FLOAT_DIVIDE = _function(
    "ratio", [("a", "number"), ("b", "number")], "number", _binary("/", _name("a"), _name("b"))
)


def test_typescript_integer_division_by_zero_no_longer_answers_infinity() -> None:
    content = emit(_ir(_DIVIDE), "typescript").content
    assert "_elmosRequireNonZero(b)" in content


def test_typescript_remainder_by_zero_no_longer_answers_nan() -> None:
    content = emit(_ir(_REMAINDER), "typescript").content
    assert "_elmosRequireNonZero(b)" in content


def test_python_integer_division_rejects_a_zero_divisor_and_the_min_over_minus_one() -> None:
    divide = _load_python(emit(_ir(_DIVIDE), "python").content, "divide")
    assert divide(-7, 2) == -3
    with pytest.raises(ZeroDivisionError, match="ELMOS_DIVIDE_BY_ZERO"):
        divide(1, 0)
    # -2^63 / -1 is the one quotient that leaves the range.
    with pytest.raises(OverflowError, match="ELMOS_INTEGER_OVERFLOW"):
        divide(INTEGER_MIN, -1)


_FLOAT_DIVISION_GUARDS: dict[Language, str] = {
    "java": "Migrated.elmosNonZero(b)",
    "csharp": "Migrated.ElmosNonZero(b)",
    "typescript": "_elmosRequireNonZero(b)",
    "react": "_elmosRequireNonZero(b)",
    "go": "elmosNonZeroFloat64(b)",
    "rust": "elmos_non_zero_f64(b)",
    "swift": "elmosNonZero(b)",
    "kotlin": "elmosNonZero(b)",
    "cpp": "elmos_non_zero(b)",
    "objc": "ElmosNonZero(b)",
    "php": "elmos_non_zero_float($b)",
    "flutter": "_elmosNonZero(b)",
}


def test_float_division_guard_fixtures_cover_every_non_python_active_target() -> None:
    assert set(_FLOAT_DIVISION_GUARDS) == set(ROUTED_LANGUAGES) - {"python"}


@pytest.mark.parametrize(("language", "expected"), _FLOAT_DIVISION_GUARDS.items())
def test_float_division_guards_the_divisor_everywhere_python_raises(
    language: Language, expected: str
) -> None:
    # Python raises on 1.0 / 0.0; the other active runtimes do not all share
    # that behavior. The canonical rule makes every supported target agree on
    # "error".
    content, planned = _emitted(_ir(_FLOAT_DIVIDE), language)
    assert planned(expected) in content


def test_python_float_division_needs_no_guard_because_it_already_raises() -> None:
    content = emit(_ir(_FLOAT_DIVIDE), "python").content
    assert "elmos_non_zero" not in content
    ratio = _load_python(content, "ratio")
    with pytest.raises(ZeroDivisionError):
        ratio(1.0, 0.0)


# --------------------------------------------------------------------------
# Differential execution over a boundary corpus
#
# A first slice of the property-testing work: the nine hand-written cases per
# route are all small positive integers, so none of the defects above was
# reachable from them. These arguments are chosen to sit on the boundaries.
# --------------------------------------------------------------------------

_BOUNDARY_ARGUMENTS = [
    (0, 0),
    (0, 1),
    (1, 0),
    (7, 2),
    (-7, 2),
    (7, -2),
    (-7, -2),
    (1, -1),
    (-1, 1),
    (SAFE_MAX, 1),
    (SAFE_MAX, -1),
    (SAFE_MAX + 1, 1),
    (INTEGER_MAX, 1),
    (INTEGER_MAX, -1),
    (INTEGER_MIN, -1),
    (INTEGER_MIN, 1),
]

_DIFFERENTIAL_UNITS = [
    ("add", _ADD),
    ("divide", _DIVIDE),
    ("rem", _REMAINDER),
    (
        "sub",
        _function(
            "sub",
            [("a", "integer"), ("b", "integer")],
            "integer",
            _binary("-", _name("a"), _name("b")),
        ),
    ),
    (
        "mul",
        _function(
            "mul",
            [("a", "integer"), ("b", "integer")],
            "integer",
            _binary("*", _name("a"), _name("b")),
        ),
    ),
]


def _load_python(source: str, name: str) -> Any:
    namespace: dict[str, Any] = {}
    exec(compile(source, "migrated.py", "exec"), namespace)  # noqa: S102 - the emitted module is the unit under test
    return namespace[name]


def _python_outcomes(source: str, name: str) -> list[Any]:
    function = _load_python(source, name)
    outcomes: list[Any] = []
    for a, b in _BOUNDARY_ARGUMENTS:
        try:
            outcomes.append(function(a, b))
        except (OverflowError, ZeroDivisionError, ValueError):
            outcomes.append("ERROR")
    return outcomes


def _typescript_outcomes(source: str, name: str) -> list[Any]:
    """Run the emitted TypeScript through Node's type stripping.

    Node is the declared runtime for this route's TypeScript target, so this
    needs no extra toolchain beyond the one the route already requires.
    """
    harness = [
        "const results: unknown[] = [];",
        f"const cases: [number, number][] = {json.dumps(_BOUNDARY_ARGUMENTS)};",
        "for (const [a, b] of cases) {",
        "  try {",
        f"    results.push({name}(a, b));",
        "  } catch {",
        '    results.push("ERROR");',
        "  }",
        "}",
        "console.log(JSON.stringify(results));",
    ]
    node = shutil.which("node")
    assert node is not None  # guarded by the test's skip marker
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "unit.ts"
        path.write_text(source + "\n" + "\n".join(harness) + "\n", encoding="utf-8")
        completed = subprocess.run(  # noqa: S603 - fixed argv, temp file input
            [node, "--experimental-strip-types", "--no-warnings", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    return json.loads(completed.stdout.strip())


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required for the TypeScript half")
@pytest.mark.parametrize(("name", "unit"), _DIFFERENTIAL_UNITS, ids=[n for n, _ in _DIFFERENTIAL_UNITS])
def test_python_and_typescript_agree_or_typescript_fails_earlier(
    name: str, unit: dict[str, Any]
) -> None:
    ir = _ir(unit)
    python = _python_outcomes(emit(ir, "python").content, name)
    typescript = _typescript_outcomes(emit(ir, "typescript").content, name)
    assert len(python) == len(typescript) == len(_BOUNDARY_ARGUMENTS)
    for arguments, expected, actual in zip(_BOUNDARY_ARGUMENTS, python, typescript, strict=True):
        if expected == actual:
            continue
        # The one documented asymmetry: a TypeScript `number` cannot represent
        # the canonical range, so it fails closed *earlier*. It may never
        # answer a different value, and it may never succeed where Python
        # failed.
        assert actual == "ERROR", f"{name}{arguments}: python={expected!r} typescript={actual!r}"
        assert expected == "ERROR" or abs(expected) > SAFE_MAX or any(
            abs(value) > SAFE_MAX for value in arguments
        ), f"{name}{arguments}: typescript failed inside the safe range"


def test_rust_integer_division_compiles_under_the_harness_warning_flags() -> None:
    # The old emission was `return (a / b);`, which rustc rejects outright with
    # `unnecessary parentheses around return value` under the `-D warnings` the
    # route harness itself passes. No corpus function divided, so no Rust route
    # ever reached it.
    content = emit(_ir(_DIVIDE), "rust").content
    assert "return (a / b);" not in content
    assert 'checked_div(b).expect("ELMOS_DIVIDE_BY_ZERO")' in content


@pytest.mark.parametrize(("language", "expected"), [("cpp", "INT64_MIN"), ("objc", "LLONG_MIN")])
def test_the_most_negative_literal_uses_the_macro_in_c_and_objective_c(
    language: str, expected: str
) -> None:
    # `-9223372036854775808LL` is unary minus applied to a constant that does
    # not fit a signed 64-bit type; GCC and Clang reject it under -Werror.
    unit = _function("least", [], "integer", {"kind": "literal", "value": INTEGER_MIN})
    assert expected in emit(_ir(unit), language).content


# --------------------------------------------------------------------------
# Grouping of the *non-arithmetic* operators
#
# The checked-arithmetic calls carry their own parentheses, so the Rust
# grouping defect no longer shows up in `(a + b) * c` even without `_group`.
# It still shows up wherever an operator is emitted infix -- which is every
# comparison and both boolean connectives. A mutation campaign found this gap:
# removing the grouping rule entirely left the suite green.
# --------------------------------------------------------------------------

_OR_THEN_AND = _function(
    "either",
    [("a", "boolean"), ("b", "boolean"), ("c", "boolean")],
    "boolean",
    _binary("&&", _binary("||", _name("a"), _name("b")), _name("c")),
)


def test_rust_groups_boolean_connectives() -> None:
    # `&&` binds tighter than `||` in Rust, so the ungrouped rendering of
    # (a || b) && c is `a || b && c`, which means a || (b && c):
    #     a=true b=false c=false   grouped -> false   ungrouped -> true
    content = emit(_ir(_OR_THEN_AND), "rust").content
    assert "a || b && c" not in content, "the reassociation defect is back for connectives"
    assert "(a || b) && c" in content


@pytest.mark.parametrize("language", ALL_TARGETS)
def test_every_target_groups_boolean_connectives(language: Language) -> None:
    content, planned = _emitted(_ir(_OR_THEN_AND), language)
    spelling = {
        "python": "(a or b) and c",
        "php": "($a || $b) && $c",
    }.get(language, "(a || b) && c")
    assert planned(spelling) in content


def test_python_rejects_arguments_outside_the_canonical_range() -> None:
    # Python and TypeScript are the only targets whose parameter type can hold
    # a value outside [-2^63, 2^63-1] at all; every other target's int64
    # cannot represent one. Without a guard the emitted Python would compute
    # happily on an argument no other target could have received.
    identity = _function("pass_through", [("a", "integer")], "integer", _name("a"))
    source = emit(_ir(identity), "python").content
    assert "_elmos_in_range(a)" in source
    function = _load_python(source, "pass_through")
    assert function(INTEGER_MAX) == INTEGER_MAX
    with pytest.raises(OverflowError, match="ELMOS_INTEGER_OVERFLOW"):
        function(INTEGER_MAX + 1)
