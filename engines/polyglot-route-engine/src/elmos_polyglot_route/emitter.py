from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field

from . import types
from .identifier_hygiene import IdentifierPlan, plan_identifiers, target_ir_view
from .models import Expression, Function, Language, RecordDefinition, RouteError, SemanticIR, Statement


@dataclass(frozen=True)
class EmittedFile:
    relative_path: str
    content: str
    normalization_rules: tuple[str, ...] = ()
    helper_digests: tuple[tuple[str, str], ...] = ()


#: Canonical type -> target spelling. `integer` is a 64-bit signed integer,
#: so it maps to the widest fixed-width integer each target has:
#:
#:   java/csharp  long   -- exact
#:   python       int    -- arbitrary precision, so exact for every value an
#:                          `integer` can hold
#:   typescript   number -- IEEE-754 binary64, exact only up to 2^53-1.
#:   javascript   JSDoc canonical names plus exact runtime guards; Node's
#:                underlying number has the same safe-integer boundary.
#:                Literals beyond it are rejected outright (see `_literal`).
#: The native exact targets:
#:
#:   cpp    std::int64_t / double / bool / std::string
#:          `/` and `%` truncate toward zero (C++11 onward) and `==` on
#:          std::string is value equality, so the canonical operators map
#:          one-to-one.
#:   objc   long long / double / BOOL / NSString *
#:          the scalars behave like C, but NSString is a *pointer*: `==`
#:          compares addresses and there is no `+`, so both are rewritten
#:          (see `_binary`).
#:   swift  Int64 / Double / Bool / String
#:          Int64 is width-stable across every supported platform, `/` and `%` truncate,
#:          and String comparison and concatenation are by value.
_TYPE_SPELLING: dict[Language, dict[str, str]] = {
    "java": {"integer": "long", "number": "double", "boolean": "boolean", "string": "String"},
    "python": {"integer": "int", "number": "float", "boolean": "bool", "string": "str"},
    "csharp": {"integer": "long", "number": "double", "boolean": "bool", "string": "string"},
    "typescript": {"integer": "number", "number": "number", "boolean": "boolean", "string": "string"},
    "react": {"integer": "number", "number": "number", "boolean": "boolean", "string": "string"},
    # JavaScript's JSDoc contract uses canonical names rather than pretending
    # its dynamic runtime has TypeScript declarations.
    "javascript": {
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "string": "string",
    },
    "go": {"integer": "int64", "number": "float64", "boolean": "bool", "string": "string"},
    "rust": {"integer": "i64", "number": "f64", "boolean": "bool", "string": "String"},
    "cpp": {
        "integer": "std::int64_t",
        "number": "double",
        "boolean": "bool",
        "string": "std::string",
    },
    "objc": {
        "integer": "long long",
        "number": "double",
        "boolean": "BOOL",
        "string": "NSString *",
    },
    "swift": {"integer": "Int64", "number": "Double", "boolean": "Bool", "string": "String"},
    # The active Flutter route deliberately emits import-free pure Dart. Dart
    # native ``int`` is the route's signed 64-bit integer; checked helpers use
    # ``BigInt`` intermediates so VM wraparound can never become a wrong value.
    "flutter": {"integer": "int", "number": "double", "boolean": "bool", "string": "String"},
    # Kotlin/JVM: `Long` is the same 64-bit signed integer Java's `long` is, and
    # `Double` the same binary64. Emission targets the JVM, so the arithmetic
    # semantics below are Java's.
    "kotlin": {"integer": "Long", "number": "Double", "boolean": "Boolean", "string": "String"},
    # PHP's `int` is platform-width; the toolchain probe asserts PHP_INT_SIZE == 8,
    # so this spelling is the canonical 64-bit signed integer, and `float` is
    # binary64 on every build the probe accepts.
    "php": {"integer": "int", "number": "float", "boolean": "bool", "string": "string"},
}

#: Languages whose emitted source is brace-delimited and statement-terminated
#: with `;`. Swift is brace-delimited but takes no terminator.
_BRACE_LANGUAGES = frozenset(
    {
        "java",
        "csharp",
        "typescript",
        "react",
        "javascript",
        "go",
        "rust",
        "cpp",
        "objc",
        "swift",
        "php",
        "flutter",
    }
)
_SEMICOLON_LANGUAGES = frozenset(
    {"java", "csharp", "typescript", "react", "javascript", "rust", "cpp", "objc", "php", "flutter"}
)

#: Targets that place the function body inside a type declaration, so the
#: body is indented one extra level.
_WRAPPED_IN_TYPE = frozenset({"java", "csharp"})

#: Canonical arithmetic rules the certified subset now declares explicitly.
#: Both were divergences the previous emitter left uncompensated, so the same
#: IR produced different observable behaviour per target:
#:
#: R1 INTEGER OVERFLOW IS AN ERROR.
#:    `+`, `-` and `*` on two `integer` operands whose exact mathematical
#:    result leaves [-2^63, 2^63-1] must fail loudly. Uncompensated this was
#:    wrap-around in Java/C#/Go, a panic in Rust (debug) but a wrap in release,
#:    an exact arbitrary-precision result in Python, and undefined behaviour in
#:    C++/Objective-C. TypeScript cannot represent the range at all, so it
#:    fails *earlier*, at 2^53-1 -- a narrower domain, never a wrong answer.
#:
#: R2 DIVISION OR REMAINDER BY ZERO IS AN ERROR.
#:    Uncompensated, `a / 0` on integers threw in Java/C#/Python, panicked in
#:    Go/Rust/Swift, was undefined behaviour in C++/Objective-C, and produced
#:    `Infinity` in TypeScript -- a silent wrong value. On floats the odd one
#:    out is the other way round: every target yields IEEE Infinity/NaN while
#:    Python raises. The canonical rule makes every supported target agree on
#:    "error".
#:    `INT64_MIN / -1` and `INT64_MIN % -1` overflow the result type and are
#:    errors under the same rule.
_OVERFLOW_MESSAGE = "ELMOS_INTEGER_OVERFLOW"
_DIVIDE_BY_ZERO_MESSAGE = "ELMOS_DIVIDE_BY_ZERO"

#: Python's `//` floors and its `%` follows the sign of the divisor; Java, C#
#: and TypeScript truncate toward zero. The canonical `/` and `%` on two
#: integers are defined as the truncating pair, so a Python target gets these
#: helpers instead of a bare operator. They are emitted only when used.
_PYTHON_HELPERS: dict[str, str] = {
    "integer_range": (
        "_ELMOS_INTEGER_MIN = -(2 ** 63)\n"
        "_ELMOS_INTEGER_MAX = 2 ** 63 - 1\n"
        "\n"
        "\n"
        "def _elmos_in_range(value: int) -> int:\n"
        '    """Canonical `integer` is a 64-bit signed integer (rule R1).\n'
        "\n"
        "    Python's int is arbitrary precision, so a result no other target\n"
        "    can hold has to be rejected here rather than silently succeed.\n"
        '    """\n'
        "    if not _ELMOS_INTEGER_MIN <= value <= _ELMOS_INTEGER_MAX:\n"
        f'        raise OverflowError("{_OVERFLOW_MESSAGE}")\n'
        "    return value\n"
    ),
    "checked_add": (
        "def _elmos_checked_add(left: int, right: int) -> int:\n    return _elmos_in_range(left + right)\n"
    ),
    "checked_sub": (
        "def _elmos_checked_sub(left: int, right: int) -> int:\n    return _elmos_in_range(left - right)\n"
    ),
    "checked_mul": (
        "def _elmos_checked_mul(left: int, right: int) -> int:\n    return _elmos_in_range(left * right)\n"
    ),
    "truncating_div": (
        "def _elmos_truncating_div(left: int, right: int) -> int:\n"
        '    """Integer division truncating toward zero, as in Java/C#/TypeScript.\n'
        "\n"
        "    Python's // floors instead: -7 // 2 is -4 where Java's -7 / 2 is -3.\n"
        "    A zero divisor is an error (rule R2) and so is the one quotient that\n"
        "    leaves the 64-bit range, -2^63 / -1.\n"
        '    """\n'
        "    if right == 0:\n"
        f'        raise ZeroDivisionError("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    quotient = abs(left) // abs(right)\n"
        "    return _elmos_in_range(quotient if (left >= 0) == (right >= 0) else -quotient)\n"
    ),
    "truncating_mod": (
        "def _elmos_truncating_mod(left: int, right: int) -> int:\n"
        '    """Remainder matching truncating division, as in Java/C#/TypeScript.\n'
        "\n"
        "    Python's % takes the sign of the divisor: -7 % 2 is 1 where Java's\n"
        "    -7 % 2 is -1. The zero-divisor and -2^63 % -1 errors come from\n"
        "    _elmos_truncating_div, which this is defined in terms of.\n"
        '    """\n'
        "    return left - _elmos_truncating_div(left, right) * right\n"
    ),
}


#: A TypeScript `number` is IEEE-754 binary64, so it stops representing
#: consecutive integers past 2^53-1 -- 9007199254740993 silently becomes
#: 9007199254740992. Integer literals beyond that range are rejected outright
#: (see `_integer_literal`), but a *runtime* value can still arrive through a
#: parameter or grow out of range inside an expression. `safe_integer` turns
#: that silent precision loss into a loud RangeError at the exact boundary.
#: `non_zero` implements rule R2: TypeScript is the only target whose `/` and
#: `%` answer Infinity/NaN instead of failing.
_TYPESCRIPT_HELPERS: dict[str, str] = {
    "safe_integer": (
        "function _elmosRequireSafeInteger(value: number): number {\n"
        "  if (!Number.isSafeInteger(value)) {\n"
        "    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);\n"
        "  }\n"
        "  return Object.is(value, -0) ? 0 : value;\n"
        "}"
    ),
    "finite_number": (
        "function _elmosRequireFiniteNumber(value: number): number {\n"
        '  if (typeof value !== "number" || !Number.isFinite(value)) {\n'
        '    throw new TypeError("ELMOS_NUMBER_NOT_FINITE");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
    "non_zero": (
        "function _elmosRequireNonZero(value: number): number {\n"
        "  if (value === 0) {\n"
        f'    throw new RangeError("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
}


#: Node.js executes JavaScript JSDoc as documentation, not as a runtime type
#: system.  Every parameter and return therefore crosses one of these exact
#: guards.  Arithmetic is guarded again at each operation so overflow to an
#: imprecise integer or a non-finite binary64 result cannot be returned as if
#: it belonged to the canonical domain.
_JAVASCRIPT_HELPERS: dict[str, str] = {
    "safe_integer": (
        "function _elmosRequireSafeInteger(value) {\n"
        "  if (!Number.isSafeInteger(value)) {\n"
        f'    throw new RangeError("{_OVERFLOW_MESSAGE}");\n'
        "  }\n"
        "  return Object.is(value, -0) ? 0 : value;\n"
        "}"
    ),
    "finite_number": (
        "function _elmosRequireFiniteNumber(value) {\n"
        '  if (typeof value !== "number" || !Number.isFinite(value)) {\n'
        '    throw new TypeError("ELMOS_NUMBER_NOT_FINITE");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
    "exact_boolean": (
        "function _elmosRequireBoolean(value) {\n"
        '  if (typeof value !== "boolean") {\n'
        '    throw new TypeError("ELMOS_BOOLEAN_REQUIRED");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
    "exact_string": (
        "function _elmosRequireString(value) {\n"
        '  if (typeof value !== "string") {\n'
        '    throw new TypeError("ELMOS_STRING_REQUIRED");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
    "non_zero": (
        "function _elmosRequireNonZero(value) {\n"
        "  if (value === 0) {\n"
        f'    throw new RangeError("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
    "exact_record": (
        "function _elmosRequireRecord(value) {\n"
        '  if (typeof value !== "object" || value === null) {\n'
        '    throw new TypeError("ELMOS_RECORD_REQUIRED");\n'
        "  }\n"
        "  return value;\n"
        "}"
    ),
}


#: Go has no checked arithmetic and no exceptions: `+` wraps silently and
#: `MinInt64 / -1` wraps to MinInt64 rather than trapping. Only `/ 0` and
#: `% 0` panic natively. These helpers implement R1 and R2 with panics, which
#: is the failure mode the Go target already has for a zero divisor.
_GO_HELPERS: dict[str, str] = {
    "integer_min": "const elmosIntegerMin int64 = -9223372036854775808",
    "checked_add": (
        "func elmosCheckedAdd(left int64, right int64) int64 {\n"
        "    sum := left + right\n"
        "    if (right > 0 && sum < left) || (right < 0 && sum > left) {\n"
        f'        panic("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return sum\n"
        "}"
    ),
    "checked_sub": (
        "func elmosCheckedSub(left int64, right int64) int64 {\n"
        "    difference := left - right\n"
        "    if (right < 0 && difference < left) || (right > 0 && difference > left) {\n"
        f'        panic("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return difference\n"
        "}"
    ),
    "checked_mul": (
        "func elmosCheckedMul(left int64, right int64) int64 {\n"
        "    if left == 0 || right == 0 {\n"
        "        return 0\n"
        "    }\n"
        "    if (left == -1 && right == elmosIntegerMin) || (right == -1 && left == elmosIntegerMin) {\n"
        f'        panic("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    product := left * right\n"
        "    if product/right != left {\n"
        f'        panic("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return product\n"
        "}"
    ),
    "checked_div": (
        "func elmosCheckedDiv(left int64, right int64) int64 {\n"
        "    if right == 0 {\n"
        f'        panic("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    if left == elmosIntegerMin && right == -1 {\n"
        f'        panic("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return left / right\n"
        "}"
    ),
    "checked_mod": (
        "func elmosCheckedMod(left int64, right int64) int64 {\n"
        "    if right == 0 {\n"
        f'        panic("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    if left == elmosIntegerMin && right == -1 {\n"
        f'        panic("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return left % right\n"
        "}"
    ),
    "non_zero_float": (
        "func elmosNonZeroFloat64(value float64) float64 {\n"
        "    if value == 0 {\n"
        f'        panic("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    return value\n"
        "}"
    ),
}


#: Java has Math.addExact/subtractExact/multiplyExact since 8, but no checked
#: remainder and no checked division below 18, so both are spelled out here to
#: keep the emitted source compilable on the whole declared source range.
_JAVA_HELPERS: dict[str, str] = {
    "checked_div": (
        "    private static long elmosCheckedDiv(long left, long right) {\n"
        "        if (right == 0L) {\n"
        f'            throw new ArithmeticException("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "        }\n"
        "        if (left == Long.MIN_VALUE && right == -1L) {\n"
        f'            throw new ArithmeticException("{_OVERFLOW_MESSAGE}");\n'
        "        }\n"
        "        return left / right;\n"
        "    }"
    ),
    "checked_mod": (
        "    private static long elmosCheckedMod(long left, long right) {\n"
        "        if (right == 0L) {\n"
        f'            throw new ArithmeticException("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "        }\n"
        "        if (left == Long.MIN_VALUE && right == -1L) {\n"
        f'            throw new ArithmeticException("{_OVERFLOW_MESSAGE}");\n'
        "        }\n"
        "        return left % right;\n"
        "    }"
    ),
    "non_zero_double": (
        "    private static double elmosNonZero(double value) {\n"
        "        if (value == 0.0) {\n"
        f'            throw new ArithmeticException("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "        }\n"
        "        return value;\n"
        "    }"
    ),
}


#: Kotlin runs on the JVM, so `Long` arithmetic wraps and `Long.MIN_VALUE / -1L`
#: silently returns `Long.MIN_VALUE` -- identical to Java, and identical in what
#: has to be guarded. `Math.addExact` and friends are `java.lang.Math`, which
#: Kotlin/JVM imports by default, so only division, remainder and the float
#: divisor guard are spelled out. These mirror `_JAVA_HELPERS` byte-for-byte in
#: behaviour: a Kotlin target that disagreed with the Java target about
#: `Long.MIN_VALUE / -1L` would break the route matrix's own transitivity.
_KOTLIN_HELPERS: dict[str, str] = {
    "checked_div": (
        "private fun elmosCheckedDiv(left: Long, right: Long): Long {\n"
        "    if (right == 0L) {\n"
        f'        throw ArithmeticException("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    if (left == Long.MIN_VALUE && right == -1L) {\n"
        f'        throw ArithmeticException("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return left / right\n"
        "}"
    ),
    "checked_mod": (
        "private fun elmosCheckedMod(left: Long, right: Long): Long {\n"
        "    if (right == 0L) {\n"
        f'        throw ArithmeticException("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    if (left == Long.MIN_VALUE && right == -1L) {\n"
        f'        throw ArithmeticException("{_OVERFLOW_MESSAGE}")\n'
        "    }\n"
        "    return left % right\n"
        "}"
    ),
    "non_zero_double": (
        "private fun elmosNonZero(value: Double): Double {\n"
        "    if (value == 0.0) {\n"
        f'        throw ArithmeticException("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    return value\n"
        "}"
    ),
}


# Dart native integer arithmetic can wrap at the signed 64-bit boundary.
# ``BigInt`` is part of the bundled Dart SDK and provides an exact intermediate
# without adding a package dependency or an import.  Every helper is
# library-private, and emitted helper bytes are separately content-bound by
# the whole-file closure.
_DART_HELPERS: dict[str, str] = {
    "integer_range": (
        "int _elmosInIntegerRange(BigInt value) {\n"
        "  final minimum = BigInt.from(-9223372036854775808);\n"
        "  final maximum = BigInt.from(9223372036854775807);\n"
        "  if (value < minimum || value > maximum) {\n"
        f"    throw RangeError('{_OVERFLOW_MESSAGE}');\n"
        "  }\n"
        "  return value.toInt();\n"
        "}"
    ),
    "checked_add": (
        "int _elmosCheckedAdd(int left, int right) {\n"
        "  return _elmosInIntegerRange(BigInt.from(left) + BigInt.from(right));\n"
        "}"
    ),
    "checked_sub": (
        "int _elmosCheckedSub(int left, int right) {\n"
        "  return _elmosInIntegerRange(BigInt.from(left) - BigInt.from(right));\n"
        "}"
    ),
    "checked_mul": (
        "int _elmosCheckedMul(int left, int right) {\n"
        "  return _elmosInIntegerRange(BigInt.from(left) * BigInt.from(right));\n"
        "}"
    ),
    "checked_div": (
        "int _elmosCheckedDiv(int left, int right) {\n"
        "  if (right == 0) {\n"
        "    throw IntegerDivisionByZeroException();\n"
        "  }\n"
        "  if (left == -9223372036854775808 && right == -1) {\n"
        f"    throw RangeError('{_OVERFLOW_MESSAGE}');\n"
        "  }\n"
        "  return left ~/ right;\n"
        "}"
    ),
    "checked_mod": (
        "int _elmosCheckedMod(int left, int right) {\n"
        "  if (right == 0) {\n"
        "    throw IntegerDivisionByZeroException();\n"
        "  }\n"
        "  if (left == -9223372036854775808 && right == -1) {\n"
        f"    throw RangeError('{_OVERFLOW_MESSAGE}');\n"
        "  }\n"
        "  return left.remainder(right);\n"
        "}"
    ),
    "non_zero_double": (
        "double _elmosNonZero(double value) {\n"
        "  if (value == 0.0) {\n"
        f"    throw ArgumentError('{_DIVIDE_BY_ZERO_MESSAGE}');\n"
        "  }\n"
        "  return value;\n"
        "}"
    ),
}


#: C# `checked` covers +, - and *; `/` and `%` already throw
#: DivideByZeroException on a zero divisor and OverflowException on
#: long.MinValue with -1, so only the float guard is left to add.
_CSHARP_HELPERS: dict[str, str] = {
    "non_zero_double": (
        "    public static double ElmosNonZero(double value)\n"
        "    {\n"
        "        if (value == 0.0)\n"
        "        {\n"
        f'            throw new DivideByZeroException("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "        }\n"
        "        return value;\n"
        "    }"
    ),
}


#: Rust's checked_* family already implements R1 and R2 for integers, so only
#: the float divisor needs a helper. Emitted only when used: the route harness
#: compiles with `-D warnings`, which makes dead_code an error.
_RUST_HELPERS: dict[str, str] = {
    "non_zero_f64": (
        "fn elmos_non_zero_f64(value: f64) -> f64 {\n"
        "    if value == 0.0 {\n"
        f'        panic!("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "    }\n"
        "    value\n"
        "}"
    ),
}


#: Swift traps on Int64 overflow and on both integer division errors by default,
#: so only the float divisor needs a guard.
_SWIFT_HELPERS: dict[str, str] = {
    "non_zero_double": (
        "private func elmosNonZero(_ value: Double) -> Double {\n"
        "    if value == 0.0 {\n"
        f'        fatalError("{_DIVIDE_BY_ZERO_MESSAGE}")\n'
        "    }\n"
        "    return value\n"
        "}"
    ),
}


#: Signed overflow and integer division by zero are both *undefined behaviour*
#: in C and C++, so these two targets need every arm of R1 and R2 spelled out.
#: Helpers have internal linkage. They are emitted only when referenced, so
#: -Wall -Wextra -Werror cannot turn an unused internal helper into a failure.
_CPP_HELPERS: dict[str, str] = {
    "checked_add": (
        "static std::int64_t elmos_checked_add(std::int64_t left, std::int64_t right) {\n"
        "    std::int64_t result = 0;\n"
        "    if (__builtin_add_overflow(left, right, &result)) {\n"
        f'        throw std::overflow_error("{_OVERFLOW_MESSAGE}");\n'
        "    }\n"
        "    return result;\n"
        "}"
    ),
    "checked_sub": (
        "static std::int64_t elmos_checked_sub(std::int64_t left, std::int64_t right) {\n"
        "    std::int64_t result = 0;\n"
        "    if (__builtin_sub_overflow(left, right, &result)) {\n"
        f'        throw std::overflow_error("{_OVERFLOW_MESSAGE}");\n'
        "    }\n"
        "    return result;\n"
        "}"
    ),
    "checked_mul": (
        "static std::int64_t elmos_checked_mul(std::int64_t left, std::int64_t right) {\n"
        "    std::int64_t result = 0;\n"
        "    if (__builtin_mul_overflow(left, right, &result)) {\n"
        f'        throw std::overflow_error("{_OVERFLOW_MESSAGE}");\n'
        "    }\n"
        "    return result;\n"
        "}"
    ),
    "checked_div": (
        "static std::int64_t elmos_checked_div(std::int64_t left, std::int64_t right) {\n"
        "    if (right == 0) {\n"
        f'        throw std::overflow_error("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "    }\n"
        "    if (left == INT64_MIN && right == -1) {\n"
        f'        throw std::overflow_error("{_OVERFLOW_MESSAGE}");\n'
        "    }\n"
        "    return left / right;\n"
        "}"
    ),
    "checked_mod": (
        "static std::int64_t elmos_checked_mod(std::int64_t left, std::int64_t right) {\n"
        "    if (right == 0) {\n"
        f'        throw std::overflow_error("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "    }\n"
        "    if (left == INT64_MIN && right == -1) {\n"
        f'        throw std::overflow_error("{_OVERFLOW_MESSAGE}");\n'
        "    }\n"
        "    return left % right;\n"
        "}"
    ),
    "non_zero_double": (
        "static double elmos_non_zero(double value) {\n"
        "    if (value == 0.0) {\n"
        f'        throw std::overflow_error("{_DIVIDE_BY_ZERO_MESSAGE}");\n'
        "    }\n"
        "    return value;\n"
        "}"
    ),
}


#: Objective-C is C for the scalar arithmetic, so it inherits the same
#: undefined behaviour and needs the same guards; NSException is the failure
#: mode that reaches the harness.
_OBJC_HELPERS: dict[str, str] = {
    "checked_add": (
        "static long long ElmosCheckedAdd(long long left, long long right) {\n"
        "    long long result = 0;\n"
        "    if (__builtin_add_overflow(left, right, &result)) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_OVERFLOW_MESSAGE}"];\n'
        "    }\n"
        "    return result;\n"
        "}"
    ),
    "checked_sub": (
        "static long long ElmosCheckedSub(long long left, long long right) {\n"
        "    long long result = 0;\n"
        "    if (__builtin_sub_overflow(left, right, &result)) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_OVERFLOW_MESSAGE}"];\n'
        "    }\n"
        "    return result;\n"
        "}"
    ),
    "checked_mul": (
        "static long long ElmosCheckedMul(long long left, long long right) {\n"
        "    long long result = 0;\n"
        "    if (__builtin_mul_overflow(left, right, &result)) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_OVERFLOW_MESSAGE}"];\n'
        "    }\n"
        "    return result;\n"
        "}"
    ),
    "checked_div": (
        "static long long ElmosCheckedDiv(long long left, long long right) {\n"
        "    if (right == 0) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_DIVIDE_BY_ZERO_MESSAGE}"];\n'
        "    }\n"
        "    if (left == LLONG_MIN && right == -1) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_OVERFLOW_MESSAGE}"];\n'
        "    }\n"
        "    return left / right;\n"
        "}"
    ),
    "checked_mod": (
        "static long long ElmosCheckedMod(long long left, long long right) {\n"
        "    if (right == 0) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_DIVIDE_BY_ZERO_MESSAGE}"];\n'
        "    }\n"
        "    if (left == LLONG_MIN && right == -1) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_OVERFLOW_MESSAGE}"];\n'
        "    }\n"
        "    return left % right;\n"
        "}"
    ),
    "non_zero_double": (
        "static double ElmosNonZero(double value) {\n"
        "    if (value == 0.0) {\n"
        f'        [NSException raise:@"ElmosArithmeticError" format:@"{_DIVIDE_BY_ZERO_MESSAGE}"];\n'
        "    }\n"
        "    return value;\n"
        "}"
    ),
}


#: PHP does not wrap on integer overflow and it does not trap: `PHP_INT_MAX + 1`
#: silently becomes a `float`. That promotion is the *only* observable signal an
#: overflow happened, and it is exact -- `int op int` is an `int` unless the
#: mathematical result left the 64-bit range -- so `is_int` on the result is a
#: sound R1 check rather than a heuristic. Verified against PHP 8.4.21:
#: `PHP_INT_MAX + 1`, `PHP_INT_MIN - 1` and `PHP_INT_MAX * 2` all return floats.
#:
#: R2 is split. `intdiv` already throws `DivisionByZeroError` on a zero divisor
#: and `ArithmeticError` on `PHP_INT_MIN / -1`, so the division helper only
#: re-labels those with the canonical messages. `%` throws on a zero divisor but
#: answers 0 for `PHP_INT_MIN % -1` instead of failing, so that arm is a real
#: guard, not a relabelling.
#: Every class reference is written `\\ClassName`, fully qualified. Inside a
#: namespace PHP resolves an unqualified *function* or *constant* to the global
#: one when the namespaced name does not exist, but it does **not** do that for
#: a class: `new ArithmeticError` inside `namespace Elmos\\Generated\\Wu00001`
#: resolves to `Elmos\\Generated\\Wu00001\\ArithmeticError` and dies with
#: "Class not found". `assembly._place_php` puts every assembled unit in its own
#: namespace, so an unqualified spelling here would replace the canonical
#: overflow error with a class-resolution error on exactly the path these guards
#: exist for -- and only on the error path, where it is least likely to be seen.
_PHP_HELPERS: dict[str, str] = {
    "checked_add": (
        "function elmos_checked_add(int $left, int $right): int {\n"
        "    $result = $left + $right;\n"
        "    if (!is_int($result)) {\n"
        f'        throw new \\ArithmeticError(\'{_OVERFLOW_MESSAGE}\');\n'
        "    }\n"
        "    return $result;\n"
        "}"
    ),
    "checked_sub": (
        "function elmos_checked_sub(int $left, int $right): int {\n"
        "    $result = $left - $right;\n"
        "    if (!is_int($result)) {\n"
        f'        throw new \\ArithmeticError(\'{_OVERFLOW_MESSAGE}\');\n'
        "    }\n"
        "    return $result;\n"
        "}"
    ),
    "checked_mul": (
        "function elmos_checked_mul(int $left, int $right): int {\n"
        "    $result = $left * $right;\n"
        "    if (!is_int($result)) {\n"
        f'        throw new \\ArithmeticError(\'{_OVERFLOW_MESSAGE}\');\n'
        "    }\n"
        "    return $result;\n"
        "}"
    ),
    "checked_div": (
        "function elmos_checked_div(int $left, int $right): int {\n"
        "    if ($right === 0) {\n"
        f'        throw new \\DivisionByZeroError(\'{_DIVIDE_BY_ZERO_MESSAGE}\');\n'
        "    }\n"
        "    if ($left === PHP_INT_MIN && $right === -1) {\n"
        f'        throw new \\ArithmeticError(\'{_OVERFLOW_MESSAGE}\');\n'
        "    }\n"
        "    return intdiv($left, $right);\n"
        "}"
    ),
    "checked_mod": (
        "function elmos_checked_mod(int $left, int $right): int {\n"
        "    if ($right === 0) {\n"
        f'        throw new \\DivisionByZeroError(\'{_DIVIDE_BY_ZERO_MESSAGE}\');\n'
        "    }\n"
        "    if ($left === PHP_INT_MIN && $right === -1) {\n"
        f'        throw new \\ArithmeticError(\'{_OVERFLOW_MESSAGE}\');\n'
        "    }\n"
        "    return $left % $right;\n"
        "}"
    ),
    # PHP 8 throws DivisionByZeroError for `1.0 / 0.0` on its own, but `fmod`
    # answers NAN for a zero divisor. One guard covers both operators and keeps
    # the emitted normalization rule set uniform with the other targets.
    "non_zero_float": (
        "function elmos_non_zero_float(float $value): float {\n"
        "    if ($value === 0.0) {\n"
        f'        throw new \\DivisionByZeroError(\'{_DIVIDE_BY_ZERO_MESSAGE}\');\n'
        "    }\n"
        "    return $value;\n"
        "}"
    ),
}


_HELPERS: dict[Language, dict[str, str]] = {
    "python": _PYTHON_HELPERS,
    "kotlin": _KOTLIN_HELPERS,
    "typescript": _TYPESCRIPT_HELPERS,
    "react": _TYPESCRIPT_HELPERS,
    "javascript": _JAVASCRIPT_HELPERS,
    "go": _GO_HELPERS,
    "java": _JAVA_HELPERS,
    "csharp": _CSHARP_HELPERS,
    "rust": _RUST_HELPERS,
    "swift": _SWIFT_HELPERS,
    "cpp": _CPP_HELPERS,
    "objc": _OBJC_HELPERS,
    "php": _PHP_HELPERS,
    "flutter": _DART_HELPERS,
}

#: Deterministic emission order, so the same IR always produces byte-identical
#: source. `sorted()` would put `checked_add` before the range constant it
#: depends on, which only works because every reference is resolved at call
#: time -- an order that reads wrong is not worth the saved line.
_HELPER_ORDER: tuple[str, ...] = (
    "integer_min",
    "integer_range",
    "safe_integer",
    "finite_number",
    "exact_boolean",
    "exact_string",
    "non_zero",
    "non_zero_float",
    "non_zero_f64",
    "non_zero_double",
    "checked_add",
    "checked_sub",
    "checked_mul",
    "checked_div",
    "checked_mod",
    "truncating_div",
    "truncating_mod",
    "exact_record",
)


def _require_helper(context: _Context, *keys: str) -> None:
    """Record the helpers this emission needs.

    A key the target has no source for is *not* an error: it means the target
    spells that operation natively (Java's Math.addExact, C#'s checked(), Rust's
    checked_add) and there is nothing to emit. A key no target knows at all is
    a typo, and fails closed.
    """
    registry = _HELPERS.get(context.language, {})
    for key in keys:
        if key not in _HELPER_ORDER:
            raise RouteError(f"UNKNOWN_HELPER:{key}")
        if key in registry:
            context.helpers.add(key)


def _helper_sources(context: _Context) -> list[str]:
    registry = _HELPERS.get(context.language, {})
    unknown = sorted(set(context.helpers) - set(registry))
    if unknown:
        raise RouteError("UNKNOWN_HELPER:" + ",".join(unknown))
    return [registry[key] for key in _HELPER_ORDER if key in context.helpers]


@dataclass
class _Context:
    language: Language
    helpers: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    normalization_rules: set[str] = field(default_factory=set)
    records: dict[str, RecordDefinition] = field(default_factory=dict)


def _emitted_file(context: _Context, relative_path: str, content: str) -> EmittedFile:
    registry = _HELPERS.get(context.language, {})
    helper_digests = tuple(
        (
            key,
            "sha256:" + hashlib.sha256(registry[key].encode("utf-8")).hexdigest(),
        )
        for key in _HELPER_ORDER
        if key in context.helpers
    )
    return EmittedFile(
        relative_path,
        content,
        tuple(sorted(context.normalization_rules)),
        helper_digests,
    )


def _type(language: Language, value: str, records: dict[str, RecordDefinition] | None = None) -> str:
    if value in _TYPE_SPELLING.get(language, {}):
        return _TYPE_SPELLING[language][value]
    if records is not None and value in records:
        return value
    raise RouteError(f"UNSUPPORTED_TYPE_MAPPING:{language}:{value}")


def _variable(language: Language, name: str) -> str:
    """The target's spelling of a *variable* reference.

    Only PHP distinguishes a variable from a bare identifier: `$name` is the
    variable, `name` is an undefined constant, and PHP 8 makes reading one a
    fatal Error rather than the PHP 7 notice-plus-string fallback. Function
    names keep no sigil, which is why this is a separate helper from the
    identifier plan rather than a rename applied to every identifier.
    """
    return f"${name}" if language == "php" else name


def _record_definition(context: _Context, record: RecordDefinition) -> str:
    lang = context.language
    if lang == "java":
        fields_str = ", ".join(f"{_type(lang, f.type, context.records)} {f.name}" for f in record.fields)
        return f"    public record {record.name}({fields_str}) {{}}"
    if lang == "csharp":
        fields_str = ", ".join(f"{_type(lang, f.type, context.records)} {f.name}" for f in record.fields)
        return f"    public record {record.name}({fields_str});"
    if lang == "python":
        lines = ["@dataclass(frozen=True)", f"class {record.name}:"]
        for f in record.fields:
            lines.append(f"    {f.name}: {_type(lang, f.type, context.records)}")
        return "\n".join(lines)
    if lang in {"typescript", "react"}:
        lines = [f"export interface {record.name} {{"]
        for f in record.fields:
            lines.append(f"    readonly {f.name}: {_type(lang, f.type, context.records)};")
        lines.append("}")
        return "\n".join(lines)
    if lang == "javascript":
        lines = ["/**", f" * @typedef {{Object}} {record.name}"]
        for f in record.fields:
            lines.append(f" * @property {{{_type(lang, f.type, context.records)}}} {f.name}")
        lines.append(" */")
        return "\n".join(lines)
    if lang == "go":
        lines = [f"type {record.name} struct {{"]
        for f in record.fields:
            lines.append(f"    {f.name} {_type(lang, f.type, context.records)}")
        lines.append("}")
        return "\n".join(lines)
    if lang == "rust":
        lines = ["#[derive(Clone, Debug, PartialEq)]", f"pub struct {record.name} {{"]
        for f in record.fields:
            lines.append(f"    pub {f.name}: {_type(lang, f.type, context.records)},")
        lines.append("}")
        return "\n".join(lines)
    if lang == "cpp":
        lines = [f"struct {record.name} {{"]
        for f in record.fields:
            lines.append(f"    {_type(lang, f.type, context.records)} {f.name};")
        lines.append("};")
        return "\n".join(lines)
    if lang == "objc":
        lines = ["typedef struct {"]
        for f in record.fields:
            lines.append(f"    {_type(lang, f.type, context.records)} {f.name};")
        lines.append(f"}} {record.name};")
        return "\n".join(lines)
    if lang == "swift":
        lines = [f"struct {record.name}: Equatable {{"]
        for f in record.fields:
            lines.append(f"    let {f.name}: {_type(lang, f.type, context.records)}")
        lines.append("}")
        return "\n".join(lines)
    if lang == "kotlin":
        lines = [f"data class {record.name}("]
        for f in record.fields:
            lines.append(f"    val {f.name}: {_type(lang, f.type, context.records)},")
        lines.append(")")
        return "\n".join(lines)
    if lang == "flutter":
        lines = [f"class {record.name} {{"]
        for f in record.fields:
            lines.append(f"    final {_type(lang, f.type, context.records)} {f.name};")
        args_str = ", ".join(f"required this.{f.name}" for f in record.fields)
        lines.append(f"    const {record.name}({{{args_str}}});")
        lines.append("}")
        return "\n".join(lines)
    if lang == "php":
        lines = [f"final readonly class {record.name} {{", "    public function __construct("]
        for f in record.fields:
            lines.append(f"        public {_type(lang, f.type, context.records)} ${f.name},")
        lines.append("    ) {}")
        lines.append("}")
        return "\n".join(lines)
    raise RouteError(f"UNSUPPORTED_RECORD_TARGET:{lang}")


def _integer_literal(language: Language, value: int) -> str:
    if not types.INTEGER_MIN <= value <= types.INTEGER_MAX:
        raise RouteError(f"INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE:{value}")
    if language in {"typescript", "react", "javascript"} and abs(value) > types.TYPESCRIPT_SAFE_INTEGER_MAX:
        # A JavaScript/TypeScript `number` cannot hold this exactly: 9007199254740993
        # silently becomes 9007199254740992.
        raise RouteError(f"INTEGER_LITERAL_UNSAFE_FOR_{language.upper()}:{value}")
    if language == "kotlin":
        if value == types.INTEGER_MIN:
            # Kotlin has no negative literal either: `-9223372036854775808L` is
            # unary minus applied to a literal one past `Long`'s range, which
            # the compiler rejects outright.
            return "Long.MIN_VALUE"
        # Always suffixed, not just outside `Int` range. Kotlin does not widen
        # `Int` to `Long` implicitly, so a bare `90` in `Math.addExact(score, 90)`
        # looks for an `addExact(Long, Int)` overload that does not exist and
        # fails to compile -- a bug that only shows up once an integer literal
        # meets a checked-arithmetic call site.
        return f"{value}L"
    if language == "flutter":
        return str(value)
    if language in {"java", "csharp"} and not -(2**31) <= value <= 2**31 - 1:
        # Without the suffix this is an `int` literal in Java and C#, and
        # `long big() { return 9007199254740993; }` does not compile
        # ("integer number too large").
        return f"{value}L"
    if language in {"cpp", "objc"} and value == types.INTEGER_MIN:
        # There is no negative literal in C or C++: `-9223372036854775808LL` is
        # unary minus applied to 9223372036854775808LL, which does not fit a
        # signed 64-bit type. GCC and Clang report "integer constant is so
        # large that it is unsigned", which the harness compiles as an error.
        # The macro is the only spelling that works, and both headers the
        # emitted file already includes provide it.
        return "INT64_MIN" if language == "cpp" else "LLONG_MIN"
    if language in {"cpp", "objc"} and not -(2**31) <= value <= 2**31 - 1:
        # C and C++ widen an out-of-range decimal literal implicitly, but the
        # suffix makes the 64-bit intent explicit and keeps the literal's type
        # identical on every platform's `int`/`long` sizes.
        return f"{value}LL"
    if language == "php":
        # PHP has no negative literal either: `-9223372036854775808` is unary
        # minus applied to `9223372036854775808`, which overflows the int range
        # and is therefore parsed as a *float*. `PHP_INT_MIN` is the only
        # spelling that stays an int, and the toolchain probe has already
        # asserted PHP_INT_SIZE == 8 so it is exactly -2^63.
        if value == types.INTEGER_MIN:
            return "PHP_INT_MIN"
        return str(value)
    if language == "swift":
        if value == types.INTEGER_MIN:
            return "Int64.min"
        if value == types.INTEGER_MAX:
            return "Int64.max"
        return f"Int64({value})"
    return str(value)


def _string_literal(language: Language, value: str) -> str:
    encoded = json.dumps(value, ensure_ascii=False)
    if language == "objc":
        # NSString literals carry the @ prefix; the escape set inside is the
        # same C set json.dumps produces.
        return f"@{encoded}"
    if language == "php":
        # A PHP double-quoted string interpolates `$name` and `{$expr}` and does
        # not understand JSON's `\uXXXX`, so json.dumps output is unsafe here in
        # two independent ways. A single-quoted string interpolates nothing and
        # recognises exactly two escapes, `\\` and `\'`; every other byte --
        # including a literal newline and raw UTF-8 -- stands for itself.
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if language == "kotlin":
        # `$` opens a string template in Kotlin: `"a$b"` is a reference to `b`,
        # and `"a$"` alone is a compile error. Kotlin understands JSON's other
        # escapes and `\uXXXX`, so escaping the sigil is the whole difference
        # from Java -- and it is silent, not a parse failure, whenever the name
        # after it happens to resolve.
        return encoded.replace("$", "\\$")
    if language == "flutter":
        # `$` starts interpolation in a Dart string literal. JSON's remaining
        # escapes are valid Dart escapes, so only the interpolation sigil has
        # to be neutralized.
        return encoded.replace("$", "\\$")
    if language == "swift":
        # Swift spells a unicode escape `\u{XXXX}`, not JSON's `\uXXXX`.
        # ensure_ascii=False leaves printable non-ASCII raw, so this only
        # rewrites the control characters json.dumps still escapes.
        return re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: f"\\u{{{match.group(1)}}}", encoded)
    return encoded


def _literal(language: Language, value: str | int | float | bool | None) -> str:
    if isinstance(value, bool):
        if language == "python":
            return "True" if value else "False"
        if language == "objc":
            return "YES" if value else "NO"
        return "true" if value else "false"
    if isinstance(value, str):
        rendered = _string_literal(language, value)
        return f"{rendered}.to_string()" if language == "rust" else rendered
    if isinstance(value, int):
        return _integer_literal(language, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            # NaN/Infinity have no shared literal spelling across the four
            # targets (Python `float('inf')`, Java `Double.POSITIVE_INFINITY`,
            # TypeScript `Infinity`), and `str()` emits `inf`, which none of
            # them parse.
            raise RouteError(f"NON_FINITE_LITERAL_OUTSIDE_CERTIFIED_SUBSET:{value}")
        if language in {"typescript", "react", "javascript"} and value == 0.0 and math.copysign(1.0, value) < 0:
            raise RouteError(f"{language.upper()}_NEGATIVE_ZERO_LITERAL_UNSUPPORTED")
        return repr(value)
    raise RouteError("NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET")


#: Per target, per operator: the call that implements R1/R2 for integer
#: arithmetic, and the helper sources that call pulls into the emitted file.
#: An empty helper tuple means the target already ships the operation (Java's
#: Math.addExact, for instance). A target absent from this table spells the
#: whole family natively and is handled below.
_CHECKED_INTEGER_CALL: dict[Language, dict[str, tuple[str, tuple[str, ...]]]] = {
    "java": {
        "+": ("Math.addExact", ()),
        "-": ("Math.subtractExact", ()),
        "*": ("Math.multiplyExact", ()),
        "/": ("Migrated.elmosCheckedDiv", ("checked_div",)),
        "%": ("Migrated.elmosCheckedMod", ("checked_mod",)),
    },
    "kotlin": {
        # `Math` is `java.lang.Math`, default-imported on Kotlin/JVM.
        "+": ("Math.addExact", ()),
        "-": ("Math.subtractExact", ()),
        "*": ("Math.multiplyExact", ()),
        # Unqualified: Kotlin's helpers are top-level declarations, not members
        # of a wrapper type the way Java's are.
        "/": ("elmosCheckedDiv", ("checked_div",)),
        "%": ("elmosCheckedMod", ("checked_mod",)),
    },
    "flutter": {
        "+": ("_elmosCheckedAdd", ("integer_range", "checked_add")),
        "-": ("_elmosCheckedSub", ("integer_range", "checked_sub")),
        "*": ("_elmosCheckedMul", ("integer_range", "checked_mul")),
        "/": ("_elmosCheckedDiv", ("checked_div",)),
        "%": ("_elmosCheckedMod", ("checked_mod",)),
    },
    "python": {
        "+": ("_elmos_checked_add", ("integer_range", "checked_add")),
        "-": ("_elmos_checked_sub", ("integer_range", "checked_sub")),
        "*": ("_elmos_checked_mul", ("integer_range", "checked_mul")),
        "/": ("_elmos_truncating_div", ("integer_range", "truncating_div")),
        # _elmos_truncating_mod is defined in terms of the division helper.
        "%": ("_elmos_truncating_mod", ("integer_range", "truncating_div", "truncating_mod")),
    },
    "go": {
        "+": ("elmosCheckedAdd", ("checked_add",)),
        "-": ("elmosCheckedSub", ("checked_sub",)),
        "*": ("elmosCheckedMul", ("integer_min", "checked_mul")),
        "/": ("elmosCheckedDiv", ("integer_min", "checked_div")),
        "%": ("elmosCheckedMod", ("integer_min", "checked_mod")),
    },
    "cpp": {
        "+": ("elmos_checked_add", ("checked_add",)),
        "-": ("elmos_checked_sub", ("checked_sub",)),
        "*": ("elmos_checked_mul", ("checked_mul",)),
        "/": ("elmos_checked_div", ("checked_div",)),
        "%": ("elmos_checked_mod", ("checked_mod",)),
    },
    "php": {
        "+": ("elmos_checked_add", ("checked_add",)),
        "-": ("elmos_checked_sub", ("checked_sub",)),
        "*": ("elmos_checked_mul", ("checked_mul",)),
        "/": ("elmos_checked_div", ("checked_div",)),
        "%": ("elmos_checked_mod", ("checked_mod",)),
    },
    "objc": {
        "+": ("ElmosCheckedAdd", ("checked_add",)),
        "-": ("ElmosCheckedSub", ("checked_sub",)),
        "*": ("ElmosCheckedMul", ("checked_mul",)),
        "/": ("ElmosCheckedDiv", ("checked_div",)),
        "%": ("ElmosCheckedMod", ("checked_mod",)),
    },
}

#: Rust spells the whole family natively; `checked_div`/`checked_rem` return
#: None for both a zero divisor and i64::MIN / -1, which is exactly R2.
_RUST_CHECKED_METHOD: dict[str, tuple[str, str]] = {
    "+": ("checked_add", _OVERFLOW_MESSAGE),
    "-": ("checked_sub", _OVERFLOW_MESSAGE),
    "*": ("checked_mul", _OVERFLOW_MESSAGE),
    "/": ("checked_div", _DIVIDE_BY_ZERO_MESSAGE),
    "%": ("checked_rem", _DIVIDE_BY_ZERO_MESSAGE),
}

#: Guard applied to a *float* divisor, per target. Python is absent because
#: its native `/` and math.fmod already raise on a zero divisor.
_FLOAT_NON_ZERO_GUARD: dict[Language, tuple[str, str]] = {
    "java": ("Migrated.elmosNonZero", "non_zero_double"),
    "csharp": ("Migrated.ElmosNonZero", "non_zero_double"),
    "typescript": ("_elmosRequireNonZero", "non_zero"),
    "react": ("_elmosRequireNonZero", "non_zero"),
    "javascript": ("_elmosRequireNonZero", "non_zero"),
    "go": ("elmosNonZeroFloat64", "non_zero_float"),
    "rust": ("elmos_non_zero_f64", "non_zero_f64"),
    "swift": ("elmosNonZero", "non_zero_double"),
    "kotlin": ("elmosNonZero", "non_zero_double"),
    "cpp": ("elmos_non_zero", "non_zero_double"),
    "objc": ("ElmosNonZero", "non_zero_double"),
    "php": ("elmos_non_zero_float", "non_zero_float"),
    "flutter": ("_elmosNonZero", "non_zero_double"),
}


def _group(language: Language, rendered: str, top_level: bool) -> str:
    """Parenthesise an infix expression.

    Rust is the exception, and only at the outermost position: the route
    harness compiles with `-D warnings`, so `return (a + b);` and
    `if (a < b) {` are hard errors under `unused_parens`. Dropping the parens
    *everywhere* -- which is what this emitter used to do for Rust -- silently
    reassociated nested expressions: the IR for `(a + b) * c` came out as
    `a + b * c`, a wrong answer with no diagnostic on ordinary inputs.
    """
    if language == "rust" and top_level:
        return rendered
    return f"({rendered})"


def _binary(
    context: _Context,
    expression: Expression,
    environment: dict[str, str],
    *,
    top_level: bool = False,
) -> str:
    assert expression.left is not None and expression.right is not None
    language = context.language
    operator = expression.operator or ""
    left_type = types.infer(expression.left, environment, context.records)
    right_type = types.infer(expression.right, environment, context.records)
    left = _expression(context, expression.left, environment)
    right = _expression(context, expression.right, environment)
    if language == "rust":
        if left_type == "number" and right_type == "integer":
            context.normalization_rules.add("rust.cast.integer-to-number")
            right = f"({right} as f64)"
        elif left_type == "integer" and right_type == "number":
            context.normalization_rules.add("rust.cast.integer-to-number")
            left = f"({left} as f64)"
    elif language == "swift":
        # Canonical integer -> number is an explicit widening in Swift.  An
        # Int64 literal cannot otherwise participate in a Double comparison or
        # arithmetic expression, even though the same widening is implicit in
        # Java/C# and represented by a single numeric type in TypeScript.
        if left_type == "number" and right_type == "integer":
            context.normalization_rules.add("swift.cast.integer-to-number")
            right = f"Double({right})"
        elif left_type == "integer" and right_type == "number":
            context.normalization_rules.add("swift.cast.integer-to-number")
            left = f"Double({left})"
    elif language == "flutter":
        if left_type == "number" and right_type == "integer":
            context.normalization_rules.add("flutter.cast.integer-to-number")
            right = f"({right}).toDouble()"
        elif left_type == "integer" and right_type == "number":
            context.normalization_rules.add("flutter.cast.integer-to-number")
            left = f"({left}).toDouble()"
    both_integer = left_type == "integer" and right_type == "integer"

    # R1/R2 for integer arithmetic. Every arm below fails loudly on overflow,
    # a zero divisor, or -2^63 divided/remaindered by -1.
    if both_integer and operator in types.ARITHMETIC_OPERATORS:
        entry = _CHECKED_INTEGER_CALL.get(language, {}).get(operator)
        if entry is not None:
            call, helper_keys = entry
            _require_helper(context, *helper_keys)
            context.normalization_rules.add(f"{language}.integer.{operator}.call:{call}")
            return f"{call}({left}, {right})"
        if language == "rust":
            method, message = _RUST_CHECKED_METHOD[operator]
            context.normalization_rules.add(f"rust.integer.{operator}.checked-method:{method}:{message}")
            return f'({left}).{method}({right}).expect("{message}")'
        if language in {"typescript", "react", "javascript"}:
            # A TypeScript `number` cannot hold the canonical range, so the
            # honest guard is the narrower one: fail at 2^53-1 rather than
            # return a rounded value. `/` additionally has to truncate, and a
            # zero divisor has to stop being Infinity.
            _require_helper(context, "safe_integer")
            context.normalization_rules.add(f"{language}.integer.{operator}.safe-integer")
            if language == "javascript":
                context.normalization_rules.add("javascript.integer.negative-zero-normalized")
            if operator == "/":
                _require_helper(context, "non_zero")
                context.normalization_rules.add(f"{language}.integer./.truncating-non-zero")
                return f"_elmosRequireSafeInteger(Math.trunc({left} / _elmosRequireNonZero({right})))"
            if operator == "%":
                _require_helper(context, "non_zero")
                context.normalization_rules.add(f"{language}.integer.%.non-zero")
                return f"_elmosRequireSafeInteger({left} % _elmosRequireNonZero({right}))"
            return f"_elmosRequireSafeInteger({left} {operator} {right})"
        if language == "csharp":
            # checked() covers +, - and *; / and % already throw
            # DivideByZeroException and OverflowException natively.
            context.normalization_rules.add(f"csharp.integer.{operator}.checked-expression")
            return f"checked({left} {operator} {right})"
        if language == "swift":
            # Int arithmetic traps on overflow and on both division errors.
            return _group(language, f"{left} {operator} {right}", top_level)
        raise RouteError(f"UNCOMPENSATED_INTEGER_ARITHMETIC:{language}:{operator}")

    # Float division and remainder: every target but Python answers
    # Infinity/NaN where the canonical rule says "error".
    if operator in {"/", "%"} and right_type == "number":
        guard = _FLOAT_NON_ZERO_GUARD.get(language)
        if guard is not None:
            call, helper = guard
            _require_helper(context, helper)
            context.normalization_rules.add(f"{language}.number.{operator}.non-zero:{call}")
            right = f"{call}({right})"

    if operator == "%":
        if language == "python":
            # Float remainder: Python's % floors here too (-7.5 % 2 is 0.5,
            # where Java, C# and TypeScript all answer -1.5). math.fmod is the
            # truncating form and matches the other three exactly.
            context.imports.add("math")
            context.normalization_rules.add("python.number.%.math-fmod")
            return f"math.fmod({left}, {right})"
        if language == "php":
            # PHP's `%` is an *integer* operator: it casts both operands to int
            # first, so `7.5 % 2` is 1, not 1.5. `fmod` is the truncating float
            # remainder and matches Java/C#/TypeScript exactly. Verified on PHP
            # 8.4.21: `fmod(-7.5, 2.0)` is -1.5, the same answer Java gives.
            context.normalization_rules.add("php.number.%.fmod")
            return f"fmod({left}, {right})"
        if language == "rust":
            # Rust has no `%` on f64 through the operator alone in the way the
            # other targets do -- `%` *is* the truncating remainder, so it maps
            # directly, but it still needs grouping like any other infix form.
            return _group(language, f"{left} % {right}", top_level)
        if language == "flutter":
            context.normalization_rules.add("flutter.number.%.remainder")
            return f"({left}).remainder({right})"
        value = _group(language, f"{left} % {right}", top_level)
        if language in {"typescript", "react", "javascript"} and "number" in {left_type, right_type}:
            _require_helper(context, "finite_number")
            context.normalization_rules.add(f"{language}.number.%.finite-result")
            return f"_elmosRequireFiniteNumber({value})"
        return value

    if operator in types.EQUALITY_OPERATORS and left_type == "string" and language == "java":
        # Java's == on String compares references, so two equal strings that
        # are not the same object answer false. Every other target here
        # compares by value.
        equality = f"{left}.equals({right})"
        context.normalization_rules.add(f"java.string.{operator}.value-equality")
        return f"({equality})" if operator == "==" else f"(!{equality})"

    if left_type == "string" and language == "objc":
        # NSString * is a pointer: `==` compares addresses, and there is no
        # `+` operator at all. Both have to become message sends.
        if operator in types.EQUALITY_OPERATORS:
            equality = f"[{left} isEqualToString:{right}]"
            return f"({equality})" if operator == "==" else f"(!{equality})"
        if operator == "+":
            return f"[{left} stringByAppendingString:{right}]"

    if language == "php":
        if operator == "+" and left_type == "string" and right_type == "string":
            # PHP concatenates with `.`; `+` on two strings is a TypeError under
            # PHP 8, not a concatenation.
            context.normalization_rules.add("php.string.+.concatenation")
            return _group(language, f"{left} . {right}", top_level)
        if operator in types.EQUALITY_OPERATORS:
            # `==` type-juggles: `'1' == '01'` and `'10' == '1e1'` are both true
            # on PHP 8.4. `===` is the value comparison every other target
            # performs -- but it also compares *types*, so `1 === 1.0` is false
            # where the canonical rule says the widened comparison is true. The
            # one mixed case the type lattice admits is integer/number, so the
            # integer side is widened explicitly before the strict compare.
            context.normalization_rules.add(f"php.equality.{operator}.strict")
            if left_type != right_type:
                context.normalization_rules.add("php.equality.integer-to-number")
                if left_type == "integer":
                    left = f"(float)({left})"
                else:
                    right = f"(float)({right})"
            rendered = {"==": "===", "!=": "!=="}[operator]
            return _group(language, f"{left} {rendered} {right}", top_level)

    rendered = operator
    if language == "python":
        rendered = {"&&": "and", "||": "or"}.get(operator, operator)
    elif language in {"typescript", "react", "javascript"}:
        # Strict equality only: JavaScript's == applies type coercion.
        if operator in types.EQUALITY_OPERATORS:
            context.normalization_rules.add(f"{language}.equality.{operator}.strict")
        rendered = {"==": "===", "!=": "!=="}.get(operator, operator)
    value = _group(language, f"{left} {rendered} {right}", top_level)
    if (
        language in {"typescript", "react", "javascript"}
        and operator in types.ARITHMETIC_OPERATORS
        and "number"
        in {
            left_type,
            right_type,
        }
    ):
        _require_helper(context, "finite_number")
        context.normalization_rules.add(f"{language}.number.{operator}.finite-result")
        return f"_elmosRequireFiniteNumber({value})"
    return value


def _expression(
    context: _Context,
    expression: Expression,
    environment: dict[str, str],
    *,
    top_level: bool = False,
) -> str:
    if expression.kind == "name":
        name = str(expression.value)
        if name not in environment:
            raise RouteError(f"UNDECLARED_NAME:{name}")
        return _variable(context.language, name)
    if expression.kind == "literal":
        if context.language == "rust" and isinstance(expression.value, str):
            context.normalization_rules.add("rust.string.literal.to-string")
        return _literal(context.language, expression.value)
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        return _binary(context, expression, environment, top_level=top_level)
    if expression.kind == "member_access":
        if expression.target is None or expression.member is None:
            raise RouteError("INVALID_MEMBER_ACCESS_EXPRESSION")
        target_str = _expression(context, expression.target, environment)
        if expression.target.kind == "binary":
            target_str = f"({target_str})"
        member = expression.member
        if context.language == "java":
            return f"{target_str}.{member}()"
        if context.language == "php":
            return f"{target_str}->{member}"
        return f"{target_str}.{member}"
    if expression.kind == "record_construct":
        if expression.record_name is None:
            raise RouteError("INVALID_RECORD_CONSTRUCT_EXPRESSION")
        if expression.record_name not in context.records:
            raise RouteError(f"UNKNOWN_RECORD_TYPE:{expression.record_name}")
        rec = context.records[expression.record_name]
        arg_map = dict(expression.arguments)
        ordered_args = [
            (f.name, _expression(context, arg_map[f.name], environment))
            for f in rec.fields
        ]
        lang = context.language
        if lang in {"java", "csharp"}:
            args_str = ", ".join(v for _, v in ordered_args)
            return f"new {rec.name}({args_str})"
        if lang == "python":
            args_str = ", ".join(f"{k}={v}" for k, v in ordered_args)
            return f"{rec.name}({args_str})"
        if lang in {"typescript", "react", "javascript"}:
            args_str = ", ".join(f"{k}: {v}" for k, v in ordered_args)
            return f"({{ {args_str} }})"
        if lang == "go":
            args_str = ", ".join(f"{k}: {v}" for k, v in ordered_args)
            return f"{rec.name}{{{args_str}}}"
        if lang == "rust":
            args_str = ", ".join(f"{k}: {v}" for k, v in ordered_args)
            return f"{rec.name} {{ {args_str} }}"
        if lang == "cpp":
            args_str = ", ".join(v for _, v in ordered_args)
            return f"{rec.name}{{{args_str}}}"
        if lang == "objc":
            args_str = ", ".join(f".{k} = {v}" for k, v in ordered_args)
            return f"({rec.name}){{{args_str}}}"
        if lang == "swift":
            args_str = ", ".join(f"{k}: {v}" for k, v in ordered_args)
            return f"{rec.name}({args_str})"
        if lang == "kotlin":
            args_str = ", ".join(v for _, v in ordered_args)
            return f"{rec.name}({args_str})"
        if lang == "flutter":
            args_str = ", ".join(f"{k}: {v}" for k, v in ordered_args)
            return f"{rec.name}({args_str})"
        if lang == "php":
            args_str = ", ".join(v for _, v in ordered_args)
            return f"new {rec.name}({args_str})"
        raise RouteError(f"UNSUPPORTED_RECORD_CONSTRUCT_TARGET:{lang}")
    raise RouteError(f"UNSUPPORTED_EMISSION_EXPRESSION:{expression.kind}")


#: How each target spells a single-assignment local binding.
#:
#: The immutable spelling is chosen wherever the language has one -- Java's
#: `final`, Rust and Swift's `let`, Kotlin's `val`, C++/Objective-C's `const`,
#: TypeScript's `const`. The IR guarantees the name is bound once, so a target
#: that can say so in its own syntax should: it keeps the emitted file honest
#: for a human reader and lets the target's own compiler enforce what the IR
#: only promises. C#, Go, Python and PHP have no local-immutability keyword,
#: so they get the plain declaration.
_LET_SPELLING: dict[Language, str] = {
    "java": "final {type} {name} = {value}",
    "csharp": "{type} {name} = {value}",
    "python": "{name}: {type} = {value}",
    "typescript": "const {name}: {type} = {value}",
    "react": "const {name}: {type} = {value}",
    "javascript": "const {name} = {value}",
    "go": "var {name} {type} = {value}",
    "rust": "let {name}: {type} = {value}",
    "cpp": "const {type} {name} = {value}",
    "objc": "const {type} {name} = {value}",
    "swift": "let {name}: {type} = {value}",
    "php": "{name} = {value}",
    "kotlin": "val {name}: {type} = {value}",
    "flutter": "final {type} {name} = {value}",
}


def _statements(
    context: _Context,
    statements: tuple[Statement, ...],
    environment: dict[str, str],
    indent: int,
    return_type: str,
) -> list[str]:
    unit = "    "
    prefix = unit * indent
    language = context.language
    lines: list[str] = []
    for statement in statements:
        if statement.kind == "let" and statement.expression is not None:
            if statement.name is None or statement.declared_type is None:
                raise RouteError("UNSUPPORTED_EMISSION_STATEMENT:let")
            try:
                spelling = _LET_SPELLING[language]
            except KeyError as error:
                raise RouteError(f"LET_EMISSION_UNSUPPORTED:{language}") from error
            suffix = ";" if language in _SEMICOLON_LANGUAGES else ""
            value = _expression(context, statement.expression, environment, top_level=True)
            lines.append(
                prefix
                + spelling.format(
                    type=_type(language, statement.declared_type, context.records),
                    name=_variable(language, statement.name),
                    value=value,
                )
                + suffix
            )
            # The binding is visible to every statement after it in this block.
            # `environment` is this block's own dict -- `if` bodies below are
            # handed a copy, which is what keeps a branch-local binding from
            # leaking past the branch in targets that would not compile it.
            environment[statement.name] = statement.declared_type
            continue
        if statement.kind == "return" and statement.expression is not None:
            suffix = ";" if language in _SEMICOLON_LANGUAGES else ""
            value = _expression(context, statement.expression, environment, top_level=True)
            if (
                language in {"rust", "swift", "kotlin", "flutter", "python"}
                and return_type == "number"
                and types.infer(statement.expression, environment, context.records) == "integer"
            ):
                if language == "rust":
                    context.normalization_rules.add("rust.return.integer-to-number")
                    value = f"{value} as f64"
                elif language == "kotlin":
                    context.normalization_rules.add("kotlin.return.integer-to-number")
                    value = f"({value}).toDouble()"
                elif language == "flutter":
                    context.normalization_rules.add("flutter.return.integer-to-number")
                    value = f"({value}).toDouble()"
                elif language == "python":
                    context.normalization_rules.add("python.return.integer-to-number")
                    value = f"float({value})"
                else:
                    context.normalization_rules.add("swift.return.integer-to-number")
                    value = f"Double({value})"
            if language in {"typescript", "react", "javascript"} and return_type == "integer":
                _require_helper(context, "safe_integer")
                context.normalization_rules.add(f"{language}.return.integer.safe-integer")
                if language == "javascript":
                    context.normalization_rules.add("javascript.return.integer.negative-zero-normalized")
                value = f"_elmosRequireSafeInteger({value})"
            elif language in {"typescript", "react", "javascript"} and return_type == "number":
                _require_helper(context, "finite_number")
                context.normalization_rules.add(f"{language}.return.number.finite")
                value = f"_elmosRequireFiniteNumber({value})"
            elif language == "javascript" and return_type == "boolean":
                _require_helper(context, "exact_boolean")
                context.normalization_rules.add("javascript.return.boolean.exact")
                value = f"_elmosRequireBoolean({value})"
            elif language == "javascript" and return_type == "string":
                _require_helper(context, "exact_string")
                context.normalization_rules.add("javascript.return.string.exact")
                value = f"_elmosRequireString({value})"
            lines.append(f"{prefix}return {value}{suffix}")
            continue
        if statement.kind == "if" and statement.condition is not None:
            condition = _expression(context, statement.condition, environment, top_level=True)
            if language == "python":
                lines.append(f"{prefix}if {condition}:")
                lines.extend(_statements(context, statement.then_body, dict(environment), indent + 1, return_type))
                if statement.else_body:
                    lines.append(f"{prefix}else:")
                    lines.extend(_statements(context, statement.else_body, dict(environment), indent + 1, return_type))
            elif language in {"go", "rust"}:
                lines.append(f"{prefix}if {condition} {{")
                lines.extend(_statements(context, statement.then_body, dict(environment), indent + 1, return_type))
                if statement.else_body:
                    # Go's semicolon rule inserts a `;` at the newline after a
                    # closing brace, which strands the `else` and makes the file
                    # fail to parse -- `unexpected keyword else, expected }`.
                    # The brace and the keyword therefore have to share a line.
                    # Rust has no such rule, so its existing shape is kept: it
                    # was already valid, and rewriting it would churn evidence
                    # for every emission that has an else branch.
                    if language == "go":
                        lines.append(f"{prefix}}} else {{")
                    else:
                        lines.append(f"{prefix}}}")
                        lines.append(f"{prefix}else {{")
                    lines.extend(_statements(context, statement.else_body, dict(environment), indent + 1, return_type))
                    lines.append(f"{prefix}}}")
                else:
                    lines.append(f"{prefix}}}")
            else:
                lines.append(f"{prefix}if ({condition}) {{")
                lines.extend(_statements(context, statement.then_body, dict(environment), indent + 1, return_type))
                lines.append(f"{prefix}}}")
                if statement.else_body:
                    lines.append(f"{prefix}else {{")
                    lines.extend(_statements(context, statement.else_body, dict(environment), indent + 1, return_type))
                    lines.append(f"{prefix}}}")
            continue
        if statement.kind == "while" and statement.condition is not None:
            condition = _expression(context, statement.condition, environment, top_level=True)
            if language == "python":
                lines.append(f"{prefix}while {condition}:")
                lines.extend(_statements(context, statement.body, dict(environment), indent + 1, return_type))
            elif language == "go":
                lines.append(f"{prefix}for {condition} {{")
                lines.extend(_statements(context, statement.body, dict(environment), indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language in {"rust", "swift"}:
                lines.append(f"{prefix}while {condition} {{")
                lines.extend(_statements(context, statement.body, dict(environment), indent + 1, return_type))
                lines.append(f"{prefix}}}")
            else:
                lines.append(f"{prefix}while ({condition}) {{")
                lines.extend(_statements(context, statement.body, dict(environment), indent + 1, return_type))
                lines.append(f"{prefix}}}")
            continue
        if statement.kind == "for":
            if statement.name is None or statement.start is None or statement.end is None:
                raise RouteError("UNSUPPORTED_EMISSION_STATEMENT:for")
            var_name = _variable(language, statement.name)
            start = _expression(context, statement.start, environment, top_level=True)
            end = _expression(context, statement.end, environment, top_level=True)
            step = _expression(context, statement.step, environment, top_level=True) if statement.step is not None else None
            loop_env = dict(environment)
            loop_env[statement.name] = "integer"
            inc = f"{var_name}++" if step is None else f"{var_name} += {step}"
            if language == "python":
                range_expr = f"range({start}, {end})" if step is None else f"range({start}, {end}, {step})"
                lines.append(f"{prefix}for {var_name} in {range_expr}:")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
            elif language == "go":
                lines.append(f"{prefix}for {var_name} := int64({start}); {var_name} < {end}; {inc} {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language == "rust":
                range_expr = f"{start}..{end}" if step is None else f"({start}..{end}).step_by({step} as usize)"
                lines.append(f"{prefix}for {var_name} in {range_expr} {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language == "swift":
                range_expr = f"{start}..<{end}" if step is None else f"stride(from: {start}, to: {end}, by: {step})"
                lines.append(f"{prefix}for {var_name} in {range_expr} {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language == "kotlin":
                range_expr = f"{start} until {end}" if step is None else f"{start} until {end} step {step}"
                lines.append(f"{prefix}for ({var_name} in {range_expr}) {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language in {"typescript", "react"}:
                lines.append(f"{prefix}for (let {var_name}: number = {start}; {var_name} < {end}; {inc}) {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language == "javascript":
                lines.append(f"{prefix}for (let {var_name} = {start}; {var_name} < {end}; {inc}) {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            elif language == "php":
                lines.append(f"{prefix}for ({var_name} = {start}; {var_name} < {end}; {inc}) {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            else:
                type_spelling = _type(language, "integer", context.records)
                lines.append(f"{prefix}for ({type_spelling} {var_name} = {start}; {var_name} < {end}; {inc}) {{")
                lines.extend(_statements(context, statement.body, loop_env, indent + 1, return_type))
                lines.append(f"{prefix}}}")
            continue
        if statement.kind == "break":
            suffix = ";" if language in _SEMICOLON_LANGUAGES else ""
            lines.append(f"{prefix}break{suffix}")
            continue
        if statement.kind == "continue":
            suffix = ";" if language in _SEMICOLON_LANGUAGES else ""
            lines.append(f"{prefix}continue{suffix}")
            continue
        raise RouteError(f"UNSUPPORTED_EMISSION_STATEMENT:{statement.kind}")
    return lines


def _signature(language: Language, function: Function, records: dict[str, RecordDefinition] | None = None) -> str:
    """The target's declaration line for one certified pure function."""
    return_type = _type(language, function.return_type, records)
    if language == "python":
        parameters = ", ".join(f"{item.name}: {_type(language, item.type, records)}" for item in function.parameters)
        return f"def {function.name}({parameters}) -> {return_type}:"
    if language in {"typescript", "react"}:
        parameters = ", ".join(f"{item.name}: {_type(language, item.type, records)}" for item in function.parameters)
        return f"export function {function.name}({parameters}): {return_type} {{"
    if language == "javascript":
        documentation = ["/**"]
        documentation.extend(f" * @param {{{_type(language, item.type, records)}}} {item.name}" for item in function.parameters)
        documentation.extend((f" * @returns {{{return_type}}}", " */"))
        parameters = ", ".join(item.name for item in function.parameters)
        return "\n".join([*documentation, f"export function {function.name}({parameters}) {{"])
    if language == "go":
        parameters = ", ".join(f"{item.name} {_type(language, item.type, records)}" for item in function.parameters)
        return f"func {function.name}({parameters}) {return_type} {{"
    if language == "rust":
        parameters = ", ".join(f"{item.name}: {_type(language, item.type, records)}" for item in function.parameters)
        return f"fn {function.name}({parameters}) -> {return_type} {{"
    if language == "php":
        parameters = ", ".join(
            f"{_type(language, item.type, records)} {_variable(language, item.name)}" for item in function.parameters
        )
        return f"function {function.name}({parameters}): {return_type} {{"
    if language == "kotlin":
        parameters = ", ".join(f"{item.name}: {_type(language, item.type, records)}" for item in function.parameters)
        return f"fun {function.name}({parameters}): {return_type} {{"
    if language == "flutter":
        parameters = ", ".join(f"{_type(language, item.type, records)} {item.name}" for item in function.parameters)
        return f"{return_type} {function.name}({parameters}) {{"
    if language == "swift":
        # `_` on every parameter keeps call sites positional, which is what
        # every other target and the behaviour harness emit.
        parameters = ", ".join(f"_ {item.name}: {_type(language, item.type, records)}" for item in function.parameters)
        return f"func {function.name}({parameters}) -> {return_type} {{"
    parameters = ", ".join(
        # `NSString *name`, not `NSString * name`.
        f"{_type(language, item.type, records)}{'' if _type(language, item.type, records).endswith('*') else ' '}{item.name}"
        for item in function.parameters
    )
    if language in _WRAPPED_IN_TYPE:
        return f"    public static {return_type} {function.name}({parameters}) {{"
    return f"{return_type} {function.name}({parameters}) {{"


def _function(context: _Context, function: Function) -> str:
    language = context.language
    environment = types.check_function(function, context.records)
    lines = [_signature(language, function, context.records)]
    if language in {"typescript", "react"}:
        for parameter in function.parameters:
            if parameter.type == "integer":
                _require_helper(context, "safe_integer")
                context.normalization_rules.add(f"{language}.parameter.integer.safe-integer")
                context.normalization_rules.add(f"{language}.parameter.integer.negative-zero-normalized")
                lines.append(f"    {parameter.name} = _elmosRequireSafeInteger({parameter.name});")
    if language == "javascript":
        parameter_guards = {
            "integer": ("_elmosRequireSafeInteger", "safe_integer"),
            "number": ("_elmosRequireFiniteNumber", "finite_number"),
            "boolean": ("_elmosRequireBoolean", "exact_boolean"),
            "string": ("_elmosRequireString", "exact_string"),
        }
        for parameter in function.parameters:
            if parameter.type in parameter_guards:
                guard, helper = parameter_guards[parameter.type]
                _require_helper(context, helper)
                context.normalization_rules.add(f"javascript.parameter.{parameter.type}.exact")
                if parameter.type == "integer":
                    context.normalization_rules.add("javascript.parameter.integer.negative-zero-normalized")
                    lines.append(f"    {parameter.name} = {guard}({parameter.name});")
                else:
                    lines.append(f"    {guard}({parameter.name});")
            elif context.records and parameter.type in context.records:
                _require_helper(context, "exact_record")
                context.normalization_rules.add("javascript.parameter.record.exact")
                lines.append(f"    _elmosRequireRecord({parameter.name});")
    if language == "python":
        # Python and TypeScript are the two targets whose parameter type can
        # physically hold a value outside the canonical `integer` range --
        # every other target's `long`/`int64`/`i64` cannot represent one, so
        # the range is enforced by the type. Python's int is unbounded, so
        # without this an out-of-range argument would compute silently and
        # answer something no other target could have produced.
        for parameter in function.parameters:
            if parameter.type == "integer":
                _require_helper(context, "integer_range")
                context.normalization_rules.add("python.parameter.integer.int64-range")
                lines.append(f"    _elmos_in_range({parameter.name})")
    body_indent = 2 if language in _WRAPPED_IN_TYPE else 1
    lines.extend(_statements(context, function.body, environment, body_indent, function.return_type))
    if language == "python":
        return "\n".join(lines)
    lines.append("    }" if language in _WRAPPED_IN_TYPE else "}")
    return "\n".join(lines)


def emit(
    ir: SemanticIR,
    target: Language,
    *,
    identifier_plan: IdentifierPlan | None = None,
) -> EmittedFile:
    if ir.diagnostics:
        raise RouteError("SOURCE_DIAGNOSTICS_BLOCK_EMISSION:" + ",".join(ir.diagnostics))
    types.check(ir)
    plan = identifier_plan if identifier_plan is not None else plan_identifiers(ir, target)
    if plan.target_language != target:
        raise RouteError("IDENTIFIER_PLAN_TARGET_LANGUAGE_MISMATCH")
    emitter_ir = target_ir_view(ir, plan)
    context = _Context(
        language=target,
        records={r.name: r for r in emitter_ir.records},
    )
    records_defs = [_record_definition(context, record) for record in emitter_ir.records]
    records_str = "\n\n".join(records_defs)
    records_part = [records_str] if records_str else []
    functions = "\n\n".join(_function(context, function) for function in emitter_ir.functions)
    helpers = _helper_sources(context)
    if target == "java":
        # Java and C# put helpers inside the type, after the functions, so the
        # emitted file stays a single compilation unit with no extra class.
        body = "\n\n".join([*records_part, functions, *helpers])
        return _emitted_file(context, "Migrated.java", f"public final class Migrated {{\n{body}\n}}\n")
    if target == "csharp":
        body = "\n\n".join([*records_part, functions, *helpers])
        return _emitted_file(context, "Migrated.cs", f"public static class Migrated\n{{\n{body}\n}}\n")
    if target == "python":
        preamble = "from __future__ import annotations\n"
        if emitter_ir.records:
            preamble += "\nfrom dataclasses import dataclass\n"
        for module in sorted(context.imports):
            preamble += f"\nimport {module}\n"
        for helper in helpers:
            preamble += "\n\n" + helper
        body = "\n\n".join([*records_part, functions])
        return _emitted_file(context, "migrated.py", f"{preamble}\n\n{body}\n")
    if target == "javascript":
        body = "\n\n".join([*helpers, *records_part, functions])
        return _emitted_file(context, "migrated.mjs", body + "\n")
    if target == "go":
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.go", "package main\n\n" + body + "\n")
    if target == "rust":
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.rs", body + "\n")
    if target == "kotlin":
        # Kotlin allows top-level functions, so there is no wrapper type -- and
        # therefore no qualifier on the helper call sites, unlike Java's
        # `Migrated.elmosCheckedDiv`. The file name still carries the shared
        # `Migrated` stem so the harness locates it the same way everywhere.
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "Migrated.kt", body + "\n")
    if target == "flutter":
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.dart", body + "\n")
    if target == "cpp":
        # <cstdint> for std::int64_t and <string> for std::string: both are
        # required by the canonical type spellings, so both are always
        # included rather than guessed at per function. <stdexcept> carries
        # the overflow_error the R1/R2 guards raise.
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(
            context,
            "migrated.cpp",
            "#include <cstdint>\n#include <stdexcept>\n#include <string>\n\n" + body + "\n",
        )
    if target == "objc":
        # Foundation carries NSString, the BOOL/YES/NO spellings and NSException.
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(
            context,
            "migrated.m",
            "#import <Foundation/Foundation.h>\n\n" + body + "\n",
        )
    if target == "swift":
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.swift", body + "\n")
    if target == "php":
        # `declare(strict_types=1)` must be the first statement in the file. It
        # is what makes the emitted `int`/`float`/`bool`/`string` parameter and
        # return types enforced rather than coercive: without it PHP would
        # happily accept the string "3" for an `int` parameter and silently
        # answer something no other target could have produced.
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.php", "<?php\n\ndeclare(strict_types=1);\n\n" + body + "\n")
    if target == "typescript":
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.ts", f"{body}\n")
    if target == "react":
        body = "\n\n".join([*records_part, *helpers, functions])
        return _emitted_file(context, "migrated.tsx", f"{body}\n")
    raise RouteError(f"UNSUPPORTED_EMISSION_TARGET:{target}")
