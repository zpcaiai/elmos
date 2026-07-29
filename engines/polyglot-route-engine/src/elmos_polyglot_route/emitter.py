from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from . import types
from .models import Expression, Function, Language, RouteError, SemanticIR, Statement


@dataclass(frozen=True)
class EmittedFile:
    relative_path: str
    content: str


#: Canonical type -> target spelling. `integer` is a 64-bit signed integer,
#: so it maps to the widest fixed-width integer each target has:
#:
#:   java/csharp  long   -- exact
#:   python       int    -- arbitrary precision, so exact for every value an
#:                          `integer` can hold
#:   typescript   number -- IEEE-754 binary64, exact only up to 2^53-1.
#:                          Literals beyond that are rejected outright (see
#:                          `_literal`); values beyond it are a documented
#:                          boundary of the profile, recorded in README.md.
#: The three added targets:
#:
#:   cpp    std::int64_t / double / bool / std::string
#:          `/` and `%` truncate toward zero (C++11 onward) and `==` on
#:          std::string is value equality, so the canonical operators map
#:          one-to-one.
#:   objc   long long / double / BOOL / NSString *
#:          the scalars behave like C, but NSString is a *pointer*: `==`
#:          compares addresses and there is no `+`, so both are rewritten
#:          (see `_binary`).
#:   swift  Int / Double / Bool / String
#:          Int is 64-bit on every supported platform, `/` and `%` truncate,
#:          and String comparison and concatenation are by value.
_TYPE_SPELLING: dict[Language, dict[str, str]] = {
    "java": {"integer": "long", "number": "double", "boolean": "boolean", "string": "String"},
    "python": {"integer": "int", "number": "float", "boolean": "bool", "string": "str"},
    "csharp": {"integer": "long", "number": "double", "boolean": "bool", "string": "string"},
    "typescript": {"integer": "number", "number": "number", "boolean": "boolean", "string": "string"},
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
    "swift": {"integer": "Int", "number": "Double", "boolean": "Bool", "string": "String"},
}

#: Languages whose emitted source is brace-delimited and statement-terminated
#: with `;`. Swift is brace-delimited but takes no terminator.
_BRACE_LANGUAGES = frozenset({"java", "csharp", "typescript", "cpp", "objc", "swift"})
_SEMICOLON_LANGUAGES = frozenset({"java", "csharp", "typescript", "cpp", "objc"})

#: Targets that place the function body inside a type declaration, so the
#: body is indented one extra level.
_WRAPPED_IN_TYPE = frozenset({"java", "csharp"})

#: Python's `//` floors and its `%` follows the sign of the divisor; Java, C#
#: and TypeScript truncate toward zero. The canonical `/` and `%` on two
#: integers are defined as the truncating pair, so a Python target gets these
#: helpers instead of a bare operator. They are emitted only when used.
_PYTHON_HELPERS: dict[str, str] = {
    "truncating_div": (
        "def _elmos_truncating_div(left: int, right: int) -> int:\n"
        '    """Integer division truncating toward zero, as in Java/C#/TypeScript.\n'
        "\n"
        "    Python's // floors instead: -7 // 2 is -4 where Java's -7 / 2 is -3.\n"
        '    """\n'
        "    quotient = abs(left) // abs(right)\n"
        "    return quotient if (left >= 0) == (right >= 0) else -quotient\n"
    ),
    "truncating_mod": (
        "def _elmos_truncating_mod(left: int, right: int) -> int:\n"
        '    """Remainder matching truncating division, as in Java/C#/TypeScript.\n'
        "\n"
        "    Python's % takes the sign of the divisor: -7 % 2 is 1 where Java's\n"
        "    -7 % 2 is -1.\n"
        '    """\n'
        "    return left - _elmos_truncating_div(left, right) * right\n"
    ),
}


#: A TypeScript `number` is IEEE-754 binary64, so it stops representing
#: consecutive integers past 2^53-1 -- 9007199254740993 silently becomes
#: 9007199254740992. Integer literals beyond that range are rejected outright
#: (see `_integer_literal`), but a *runtime* value can still arrive through a
#: parameter or grow out of range inside an expression. This guard turns that
#: silent precision loss into a loud RangeError at the exact boundary, and is
#: emitted only for TypeScript targets that actually carry `integer` values.
_TYPESCRIPT_SAFE_INTEGER_HELPER = (
    "function _elmosRequireSafeInteger(value: number): number {\n"
    "  if (!Number.isSafeInteger(value)) {\n"
    "    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);\n"
    "  }\n"
    "  return value;\n"
    "}"
)


@dataclass
class _Context:
    language: Language
    helpers: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)


def _type(language: Language, value: str) -> str:
    try:
        return _TYPE_SPELLING[language][value]
    except KeyError as error:
        raise RouteError(f"UNSUPPORTED_TYPE_MAPPING:{language}:{value}") from error


def _integer_literal(language: Language, value: int) -> str:
    if not types.INTEGER_MIN <= value <= types.INTEGER_MAX:
        raise RouteError(f"INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE:{value}")
    if language == "typescript" and abs(value) > types.TYPESCRIPT_SAFE_INTEGER_MAX:
        # A TypeScript `number` cannot hold this exactly: 9007199254740993
        # silently becomes 9007199254740992.
        raise RouteError(f"INTEGER_LITERAL_UNSAFE_FOR_TYPESCRIPT:{value}")
    if language in {"java", "csharp"} and not -(2**31) <= value <= 2**31 - 1:
        # Without the suffix this is an `int` literal in Java and C#, and
        # `long big() { return 9007199254740993; }` does not compile
        # ("integer number too large").
        return f"{value}L"
    if language in {"cpp", "objc"} and not -(2**31) <= value <= 2**31 - 1:
        # C and C++ widen an out-of-range decimal literal implicitly, but the
        # suffix makes the 64-bit intent explicit and keeps the literal's type
        # identical on every platform's `int`/`long` sizes.
        return f"{value}LL"
    return str(value)


def _string_literal(language: Language, value: str) -> str:
    encoded = json.dumps(value, ensure_ascii=False)
    if language == "objc":
        # NSString literals carry the @ prefix; the escape set inside is the
        # same C set json.dumps produces.
        return f"@{encoded}"
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
        return _string_literal(language, value)
    if isinstance(value, int):
        return _integer_literal(language, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            # NaN/Infinity have no shared literal spelling across the four
            # targets (Python `float('inf')`, Java `Double.POSITIVE_INFINITY`,
            # TypeScript `Infinity`), and `str()` emits `inf`, which none of
            # them parse.
            raise RouteError(f"NON_FINITE_LITERAL_OUTSIDE_CERTIFIED_SUBSET:{value}")
        return repr(value)
    raise RouteError("NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET")


def _binary(context: _Context, expression: Expression, environment: dict[str, str]) -> str:
    assert expression.left is not None and expression.right is not None
    language = context.language
    operator = expression.operator or ""
    left_type = types.infer(expression.left, environment)
    right_type = types.infer(expression.right, environment)
    left = _expression(context, expression.left, environment)
    right = _expression(context, expression.right, environment)
    both_integer = left_type == "integer" and right_type == "integer"

    if operator == "/" and both_integer:
        if language == "python":
            context.helpers.add("truncating_div")
            return f"_elmos_truncating_div({left}, {right})"
        if language == "typescript":
            return f"Math.trunc({left} / {right})"
        return f"({left} / {right})"  # java/csharp already truncate

    if operator == "%":
        if language == "python" and both_integer:
            # _elmos_truncating_mod is defined in terms of _elmos_truncating_div,
            # so both go into the emitted module (sorted order emits div first).
            context.helpers.update({"truncating_div", "truncating_mod"})
            return f"_elmos_truncating_mod({left}, {right})"
        if language == "python":
            # Float remainder: Python's % floors here too (-7.5 % 2 is 0.5,
            # where Java, C# and TypeScript all answer -1.5). math.fmod is the
            # truncating form and matches the other three exactly.
            context.imports.add("math")
            return f"math.fmod({left}, {right})"
        return f"({left} % {right})"  # java/csharp/typescript already truncate

    if operator in types.EQUALITY_OPERATORS and left_type == "string" and language == "java":
        # Java's == on String compares references, so two equal strings that
        # are not the same object answer false. Every other target here
        # compares by value.
        equality = f"{left}.equals({right})"
        return f"({equality})" if operator == "==" else f"(!{equality})"

    if left_type == "string" and language == "objc":
        # NSString * is a pointer: `==` compares addresses, and there is no
        # `+` operator at all. Both have to become message sends.
        if operator in types.EQUALITY_OPERATORS:
            equality = f"[{left} isEqualToString:{right}]"
            return f"({equality})" if operator == "==" else f"(!{equality})"
        if operator == "+":
            return f"[{left} stringByAppendingString:{right}]"

    rendered = operator
    if language == "python":
        rendered = {"&&": "and", "||": "or"}.get(operator, operator)
    elif language == "typescript":
        # Strict equality only: TypeScript's == applies type coercion.
        rendered = {"==": "===", "!=": "!=="}.get(operator, operator)
    return f"({left} {rendered} {right})"


def _expression(context: _Context, expression: Expression, environment: dict[str, str]) -> str:
    if expression.kind == "name":
        name = str(expression.value)
        if name not in environment:
            raise RouteError(f"UNDECLARED_NAME:{name}")
        return name
    if expression.kind == "literal":
        return _literal(context.language, expression.value)
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        return _binary(context, expression, environment)
    raise RouteError(f"UNSUPPORTED_EMISSION_EXPRESSION:{expression.kind}")


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
        if statement.kind == "return" and statement.expression is not None:
            suffix = ";" if language in _SEMICOLON_LANGUAGES else ""
            value = _expression(context, statement.expression, environment)
            if language == "typescript" and return_type == "integer":
                context.helpers.add("typescript_safe_integer")
                value = f"_elmosRequireSafeInteger({value})"
            lines.append(f"{prefix}return {value}{suffix}")
            continue
        if statement.kind == "if" and statement.condition is not None:
            condition = _expression(context, statement.condition, environment)
            if language == "python":
                lines.append(f"{prefix}if {condition}:")
                lines.extend(_statements(context, statement.then_body, environment, indent + 1, return_type))
                if statement.else_body:
                    lines.append(f"{prefix}else:")
                    lines.extend(_statements(context, statement.else_body, environment, indent + 1, return_type))
            else:
                lines.append(f"{prefix}if ({condition}) {{")
                lines.extend(_statements(context, statement.then_body, environment, indent + 1, return_type))
                lines.append(f"{prefix}}}")
                if statement.else_body:
                    lines.append(f"{prefix}else {{")
                    lines.extend(_statements(context, statement.else_body, environment, indent + 1, return_type))
                    lines.append(f"{prefix}}}")
            continue
        raise RouteError(f"UNSUPPORTED_EMISSION_STATEMENT:{statement.kind}")
    return lines


def _signature(language: Language, function: Function) -> str:
    """The target's declaration line for one certified pure function."""
    return_type = _type(language, function.return_type)
    if language == "python":
        parameters = ", ".join(
            f"{item.name}: {_type(language, item.type)}" for item in function.parameters
        )
        return f"def {function.name}({parameters}) -> {return_type}:"
    if language == "typescript":
        parameters = ", ".join(
            f"{item.name}: {_type(language, item.type)}" for item in function.parameters
        )
        return f"export function {function.name}({parameters}): {return_type} {{"
    if language == "swift":
        # `_` on every parameter keeps call sites positional, which is what
        # every other target and the behaviour harness emit.
        parameters = ", ".join(
            f"_ {item.name}: {_type(language, item.type)}" for item in function.parameters
        )
        return f"func {function.name}({parameters}) -> {return_type} {{"
    parameters = ", ".join(
        # `NSString *name`, not `NSString * name`.
        f"{_type(language, item.type)}{'' if _type(language, item.type).endswith('*') else ' '}{item.name}"
        for item in function.parameters
    )
    if language in _WRAPPED_IN_TYPE:
        return f"    public static {return_type} {function.name}({parameters}) {{"
    return f"{return_type} {function.name}({parameters}) {{"


def _function(context: _Context, function: Function) -> str:
    language = context.language
    environment = types.check_function(function)
    lines = [_signature(language, function)]
    if language == "typescript":
        for parameter in function.parameters:
            if parameter.type == "integer":
                context.helpers.add("typescript_safe_integer")
                lines.append(f"    _elmosRequireSafeInteger({parameter.name});")
    body_indent = 2 if language in _WRAPPED_IN_TYPE else 1
    lines.extend(
        _statements(context, function.body, environment, body_indent, function.return_type)
    )
    if language == "python":
        return "\n".join(lines)
    lines.append("    }" if language in _WRAPPED_IN_TYPE else "}")
    return "\n".join(lines)


def emit(ir: SemanticIR, target: Language) -> EmittedFile:
    if ir.diagnostics:
        raise RouteError("SOURCE_DIAGNOSTICS_BLOCK_EMISSION:" + ",".join(ir.diagnostics))
    types.check(ir)
    context = _Context(language=target)
    functions = "\n\n".join(_function(context, function) for function in ir.functions)
    if target == "java":
        return EmittedFile("Migrated.java", f"public final class Migrated {{\n{functions}\n}}\n")
    if target == "csharp":
        return EmittedFile("Migrated.cs", f"public static class Migrated\n{{\n{functions}\n}}\n")
    if target == "python":
        preamble = "from __future__ import annotations\n"
        for module in sorted(context.imports):
            preamble += f"\nimport {module}\n"
        for name in sorted(context.helpers):
            preamble += "\n\n" + _PYTHON_HELPERS[name]
        return EmittedFile("migrated.py", f"{preamble}\n\n{functions}\n")
    if target == "cpp":
        # <cstdint> for std::int64_t and <string> for std::string: both are
        # required by the canonical type spellings, so both are always
        # included rather than guessed at per function.
        return EmittedFile(
            "migrated.cpp",
            "#include <cstdint>\n#include <string>\n\n" + functions + "\n",
        )
    if target == "objc":
        # Foundation carries NSString and the BOOL/YES/NO spellings.
        return EmittedFile(
            "migrated.m",
            "#import <Foundation/Foundation.h>\n\n" + functions + "\n",
        )
    if target == "swift":
        return EmittedFile("migrated.swift", functions + "\n")
    if "typescript_safe_integer" in context.helpers:
        return EmittedFile("migrated.ts", f"{_TYPESCRIPT_SAFE_INTEGER_HELPER}\n\n{functions}\n")
    return EmittedFile("migrated.ts", f"{functions}\n")
