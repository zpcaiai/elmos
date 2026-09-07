"""Canonical type inference for the certified expression subset.

The semantic IR carries a declared type for every parameter and return value
but not for the expressions in between, and *the target-language spelling of
an operator depends on those types*. Three examples, all reproduced against
real toolchains before this module was written:

* `a / b` on two integers truncates in Java, C# and (with `Math.trunc`)
  TypeScript, but is true division in Python -- `divide(7, 2)` returned 3 in
  Java and 3.5 in Python from the same IR, and the Python result is not even
  an `int` despite the emitted `-> int` annotation.
* `a % b` truncates toward zero in Java/C#/TypeScript and floors in Python:
  `rem(-7, 2)` is -1 in Java and 1 in Python.
* `a == b` on two strings is value equality in Python, C# and TypeScript and
  *reference* equality in Java: the same IR answered `true` in three targets
  and `false` in Java for equal-but-not-identical strings.

Emitting a faithful operator therefore requires knowing whether its operands
are integers, floats or strings, which is what `infer` computes. It is a
closed, total function over the certified subset: anything it cannot type
exactly raises `RouteError` instead of guessing.
"""
from __future__ import annotations

from .models import Expression, Function, RouteError, SemanticIR, Statement

#: The canonical type lattice. `integer` is a 64-bit signed integer,
#: `number` an IEEE-754 binary64 float.
CANONICAL_TYPES: frozenset[str] = frozenset({"integer", "number", "boolean", "string"})

NUMERIC_TYPES: frozenset[str] = frozenset({"integer", "number"})

ARITHMETIC_OPERATORS: frozenset[str] = frozenset({"+", "-", "*", "/", "%"})
ORDERING_OPERATORS: frozenset[str] = frozenset({"<", "<=", ">", ">="})
EQUALITY_OPERATORS: frozenset[str] = frozenset({"==", "!="})
LOGICAL_OPERATORS: frozenset[str] = frozenset({"&&", "||"})

#: Widest value an `integer` may take: the certified subset defines it as a
#: 64-bit signed integer because that is the widest fixed-width integer the
#: four targets share (Java/C# `long`).
INTEGER_MIN = -(2**63)
INTEGER_MAX = 2**63 - 1

#: Beyond this, IEEE-754 binary64 -- and therefore a TypeScript `number` --
#: can no longer represent consecutive integers.
TYPESCRIPT_SAFE_INTEGER_MAX = 2**53 - 1


def literal_type(value: object) -> str:
    """Canonical type of a literal. `bool` is checked first: in Python it is
    a subclass of `int`."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    raise RouteError("NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET")


def infer(expression: Expression, environment: dict[str, str]) -> str:
    """Canonical type of `expression` under `environment` (name -> type)."""
    if expression.kind == "name":
        name = str(expression.value)
        if name not in environment:
            raise RouteError(f"UNDECLARED_NAME:{name}")
        return environment[name]
    if expression.kind == "literal":
        return literal_type(expression.value)
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        operator = expression.operator or ""
        left = infer(expression.left, environment)
        right = infer(expression.right, environment)
        if operator in ARITHMETIC_OPERATORS:
            if operator == "+" and left == "string" and right == "string":
                return "string"
            if left not in NUMERIC_TYPES or right not in NUMERIC_TYPES:
                raise RouteError(f"OPERAND_TYPE_MISMATCH:{operator}:{left}:{right}")
            # Java/C# binary numeric promotion, Python's int/float promotion
            # and TypeScript's single number type all agree on this rule.
            return "number" if "number" in (left, right) else "integer"
        if operator in ORDERING_OPERATORS:
            if left == "string" or right == "string":
                # Java orders strings by UTF-16 code unit, Python by code
                # point: the two disagree for anything above the BMP. No
                # emitted comparison can be faithful in both.
                raise RouteError(f"STRING_ORDERING_OUTSIDE_CERTIFIED_SUBSET:{operator}")
            if left not in NUMERIC_TYPES or right not in NUMERIC_TYPES:
                raise RouteError(f"OPERAND_TYPE_MISMATCH:{operator}:{left}:{right}")
            return "boolean"
        if operator in EQUALITY_OPERATORS:
            if left != right and not (left in NUMERIC_TYPES and right in NUMERIC_TYPES):
                raise RouteError(f"OPERAND_TYPE_MISMATCH:{operator}:{left}:{right}")
            return "boolean"
        if operator in LOGICAL_OPERATORS:
            if left != "boolean" or right != "boolean":
                raise RouteError(f"OPERAND_TYPE_MISMATCH:{operator}:{left}:{right}")
            return "boolean"
        raise RouteError(f"UNSUPPORTED_OPERATOR:{operator}")
    raise RouteError(f"UNSUPPORTED_EXPRESSION:{expression.kind}")


def environment_of(function: Function) -> dict[str, str]:
    environment: dict[str, str] = {}
    for parameter in function.parameters:
        if parameter.name in environment:
            raise RouteError(f"DUPLICATE_PARAMETER:{parameter.name}")
        environment[parameter.name] = parameter.type
    return environment


def _check_statements(
    statements: tuple[Statement, ...], environment: dict[str, str], return_type: str
) -> None:
    """Type-check one block. `environment` is this block's scope and is mutated
    by `let`; callers hand nested blocks a copy.

    SCOPING IS BLOCK SCOPING, AND DELIBERATELY THE STRICTER RULE

    Python binds a name for the whole function, so `if c: x = 1` leaves `x`
    readable after the `if`. Go, Rust, Java, C#, C++ and Swift bind it to the
    block, where the same shape does not compile. A single IR cannot mean both,
    so it means the stricter one: a binding introduced inside a branch is gone
    at the end of that branch, and a source relying on Python's function scope
    is rejected here rather than emitted into a target that would not build.
    """
def _check_statements(
    statements: tuple[Statement, ...],
    environment: dict[str, str],
    return_type: str,
    *,
    in_loop: bool = False,
) -> None:
    for statement in statements:
        if statement.kind == "let":
            if statement.expression is None or statement.name is None:
                raise RouteError("INVALID_LET_STATEMENT")
            if statement.declared_type not in CANONICAL_TYPES:
                raise RouteError(f"UNSUPPORTED_LET_TYPE:{statement.declared_type}")
            if statement.name in environment:
                # Shadowing is refused rather than resolved. Several targets
                # forbid it outright, and where it is legal the reader has to
                # track which binding is live -- neither is worth supporting
                # when the frontend can simply pick another name.
                raise RouteError(f"LET_NAME_ALREADY_BOUND:{statement.name}")
            actual = infer(statement.expression, environment)
            if actual != statement.declared_type:
                # No integer -> number widening here. A `return` may widen
                # because every target widens identically at that boundary; a
                # binding names a value, and letting the name disagree with the
                # value's type is how a later expression silently changes which
                # arithmetic rules apply.
                raise RouteError(f"LET_TYPE_MISMATCH:{statement.declared_type}:{actual}")
            environment[statement.name] = statement.declared_type
            continue
        if statement.kind == "return" and statement.expression is not None:
            actual = infer(statement.expression, environment)
            # integer -> number is the one widening every target performs
            # identically (Java/C# implicit widening, Python int -> float,
            # TypeScript's single number type). Everything else must match.
            if actual != return_type and not (actual == "integer" and return_type == "number"):
                raise RouteError(f"RETURN_TYPE_MISMATCH:{return_type}:{actual}")
            continue
        if statement.kind == "if" and statement.condition is not None:
            if infer(statement.condition, environment) != "boolean":
                raise RouteError("CONDITION_MUST_BE_BOOLEAN")
            _check_statements(statement.then_body, dict(environment), return_type, in_loop=in_loop)
            _check_statements(statement.else_body, dict(environment), return_type, in_loop=in_loop)
            continue
        if statement.kind == "while":
            if statement.condition is None:
                raise RouteError("INVALID_WHILE_STATEMENT")
            if infer(statement.condition, environment) != "boolean":
                raise RouteError("CONDITION_MUST_BE_BOOLEAN")
            _check_statements(statement.body, dict(environment), return_type, in_loop=True)
            continue
        if statement.kind == "for":
            if statement.name is None or statement.start is None or statement.end is None:
                raise RouteError("INVALID_FOR_STATEMENT")
            if statement.declared_type != "integer":
                raise RouteError(f"UNSUPPORTED_LOOP_VARIABLE_TYPE:{statement.declared_type}")
            if statement.name in environment:
                raise RouteError(f"LET_NAME_ALREADY_BOUND:{statement.name}")
            start_type = infer(statement.start, environment)
            if start_type != "integer":
                raise RouteError(f"LOOP_BOUND_TYPE_MISMATCH:start:integer:{start_type}")
            end_type = infer(statement.end, environment)
            if end_type != "integer":
                raise RouteError(f"LOOP_BOUND_TYPE_MISMATCH:end:integer:{end_type}")
            if statement.step is not None:
                step_type = infer(statement.step, environment)
                if step_type != "integer":
                    raise RouteError(f"LOOP_BOUND_TYPE_MISMATCH:step:integer:{step_type}")
            loop_env = dict(environment)
            loop_env[statement.name] = "integer"
            _check_statements(statement.body, loop_env, return_type, in_loop=True)
            continue
        if statement.kind == "break":
            if not in_loop:
                raise RouteError("BREAK_OUTSIDE_LOOP")
            continue
        if statement.kind == "continue":
            if not in_loop:
                raise RouteError("CONTINUE_OUTSIDE_LOOP")
            continue


def check_function(function: Function) -> dict[str, str]:
    """Type-check one function and return its parameter environment."""
    if function.return_type not in CANONICAL_TYPES:
        raise RouteError(f"UNSUPPORTED_RETURN_TYPE:{function.return_type}")
    environment = environment_of(function)
    _check_statements(function.body, environment, function.return_type)
    return environment


def check(ir: SemanticIR) -> None:
    """Type-check every function in a semantic IR, fail closed on the first
    expression the canonical lattice cannot type exactly."""
    for function in ir.functions:
        check_function(function)
