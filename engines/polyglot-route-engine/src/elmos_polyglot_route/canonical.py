"""The canonical semantics of the certified subset, as an executable oracle.

Rules R1 and R2 are stated in `emitter.py` as prose and enforced there as
per-target compensations. This module is the same rules as a reference
interpreter: given a `SemanticIR` and arguments, it produces the answer every
target is required to produce, or raises `CanonicalError` where every target is
required to fail.

Having the rules executable buys three things the prose cannot:

* an oracle for targets this process cannot run. A differential test needs a
  reference; using one *target* as the reference (Python, say) tests
  target-against-target and quietly promotes one implementation to the
  specification. This is the specification.
* `evaluate` reports the widest integer any *intermediate* took, which is what
  makes the TypeScript narrowing statable. TypeScript fails whenever any
  intermediate leaves the safe-integer range, not only when an operand or the
  final result does -- `(a + b) * a - b` with a=1, b=2^53-1 answers 1 with an
  intermediate of 2^53, and TypeScript is required to fail on it.
* a place for a future construct's semantics to be pinned before any emitter
  learns to lower it.

The interpreter deliberately mirrors the *rules*, not any target: integer
arithmetic is exact and then range-checked, division truncates toward zero,
remainder takes the sign of the dividend, and a zero divisor is an error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import Expression, Function, RouteError, SemanticIR, Statement

INTEGER_MIN = -(2**63)
INTEGER_MAX = 2**63 - 1

#: Beyond this an IEEE-754 binary64 stops representing consecutive integers,
#: which is the boundary the TypeScript target fails at.
SAFE_INTEGER_MAX = 2**53 - 1


class CanonicalError(Exception):
    """Raised where the canonical rules require every target to fail."""


class IntegerOverflow(CanonicalError):
    """Rule R1: an integer result left [-2^63, 2^63-1]."""


class DivideByZero(CanonicalError):
    """Rule R2: a divisor was zero, or the quotient left the range."""


@dataclass(frozen=True)
class Evaluation:
    value: Any
    #: Widest magnitude any integer intermediate took, the final value
    #: included. `None` when the unit touched no integers at all.
    widest_integer: int | None
    #: False once any binary64 operand or intermediate becomes NaN or
    #: infinity.  The final result may still be finite (for example a boolean
    #: comparison after overflowing multiplication), so this is tracked
    #: independently from ``value``.
    all_numbers_finite: bool

    @property
    def within_safe_integers(self) -> bool:
        return self.widest_integer is None or self.widest_integer <= SAFE_INTEGER_MAX

    @property
    def within_finite_numbers(self) -> bool:
        return self.all_numbers_finite


class _Tracker:
    def __init__(self) -> None:
        self.widest: int | None = None
        self.all_numbers_finite = True

    def integer(self, value: int) -> int:
        if not INTEGER_MIN <= value <= INTEGER_MAX:
            raise IntegerOverflow(f"ELMOS_INTEGER_OVERFLOW:{value}")
        magnitude = abs(value)
        if self.widest is None or magnitude > self.widest:
            self.widest = magnitude
        return value

    def number(self, value: float) -> float:
        if not math.isfinite(value):
            self.all_numbers_finite = False
        return value


def _truncating_divide(left: int, right: int) -> int:
    """Quotient truncated toward zero, the canonical rounding.

    Python's // floors, so -7 // 2 is -4 where the canonical answer is -3.
    """
    quotient = abs(left) // abs(right)
    return quotient if (left >= 0) == (right >= 0) else -quotient


def _arithmetic(operator: str, left: Any, right: Any, tracker: _Tracker) -> Any:
    both_integer = isinstance(left, int) and isinstance(right, int)
    both_integer = both_integer and not isinstance(left, bool) and not isinstance(right, bool)
    if operator in {"/", "%"} and right == 0:
        raise DivideByZero("ELMOS_DIVIDE_BY_ZERO")
    if both_integer:
        if operator == "+":
            return tracker.integer(left + right)
        if operator == "-":
            return tracker.integer(left - right)
        if operator == "*":
            return tracker.integer(left * right)
        if operator == "/":
            return tracker.integer(_truncating_divide(left, right))
        if operator == "%":
            # Defined through the quotient, so INT64_MIN % -1 fails for the
            # same reason INT64_MIN / -1 does -- which is what makes C# and
            # Rust, whose primitives fail there, agree with everyone else.
            return tracker.integer(left - tracker.integer(_truncating_divide(left, right)) * right)
        raise RouteError(f"UNSUPPORTED_OPERATOR:{operator}")
    if operator == "+" and isinstance(left, str) and isinstance(right, str):
        return left + right
    if operator == "+":
        return tracker.number(left + right)
    if operator == "-":
        return tracker.number(left - right)
    if operator == "*":
        return tracker.number(left * right)
    if operator == "/":
        return tracker.number(left / right)
    if operator == "%":
        # Float remainder takes the sign of the dividend, like the truncating
        # integer form and unlike Python's own %.
        left_number = tracker.number(float(left))
        right_number = tracker.number(float(right))
        if not math.isfinite(left_number) or not math.isfinite(right_number):
            # Non-finite arithmetic is outside the finite-number execution
            # profile.  Preserve that tracker verdict without leaking
            # ``math.fmod``'s host-specific ValueError.
            return tracker.number(float("nan"))
        return tracker.number(math.fmod(left_number, right_number))
    raise RouteError(f"UNSUPPORTED_OPERATOR:{operator}")


def _expression(expression: Expression, environment: dict[str, Any], tracker: _Tracker) -> Any:
    if expression.kind == "name":
        name = str(expression.value)
        if name not in environment:
            raise RouteError(f"UNDECLARED_NAME:{name}")
        value = environment[name]
        if isinstance(value, int) and not isinstance(value, bool):
            tracker.integer(value)
        elif isinstance(value, float):
            tracker.number(value)
        return value
    if expression.kind == "literal":
        value = expression.value
        if isinstance(value, int) and not isinstance(value, bool):
            tracker.integer(value)
        elif isinstance(value, float):
            tracker.number(value)
        return value
    if expression.kind != "binary" or expression.left is None or expression.right is None:
        raise RouteError(f"UNSUPPORTED_EXPRESSION:{expression.kind}")
    operator = expression.operator or ""
    if operator == "&&":
        left = _expression(expression.left, environment, tracker)
        # Short-circuit, as every target does.
        return left and _expression(expression.right, environment, tracker)
    if operator == "||":
        left = _expression(expression.left, environment, tracker)
        return left or _expression(expression.right, environment, tracker)
    left = _expression(expression.left, environment, tracker)
    right = _expression(expression.right, environment, tracker)
    if operator in {"<", "<=", ">", ">=", "==", "!="}:
        return {
            "<": left < right,
            "<=": left <= right,
            ">": left > right,
            ">=": left >= right,
            "==": left == right,
            "!=": left != right,
        }[operator]
    return _arithmetic(operator, left, right, tracker)


class _Returned(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


def _statements(statements: tuple[Statement, ...], environment: dict[str, Any], tracker: _Tracker) -> None:
    for statement in statements:
        if statement.kind == "return" and statement.expression is not None:
            raise _Returned(_expression(statement.expression, environment, tracker))
        if statement.kind == "if" and statement.condition is not None:
            if _expression(statement.condition, environment, tracker):
                _statements(statement.then_body, environment, tracker)
            else:
                _statements(statement.else_body, environment, tracker)
            continue
        raise RouteError(f"UNSUPPORTED_STATEMENT:{statement.kind}")


def evaluate(function: Function, arguments: list[Any]) -> Evaluation:
    """Run one function under the canonical rules.

    Raises `CanonicalError` exactly where every target is required to fail, and
    `RouteError` where the IR is outside the certified subset.
    """
    if len(arguments) != len(function.parameters):
        raise RouteError("ARGUMENT_COUNT_MISMATCH")
    tracker = _Tracker()
    environment: dict[str, Any] = {}
    for parameter, argument in zip(function.parameters, arguments, strict=True):
        if parameter.type == "integer":
            tracker.integer(argument)
        elif parameter.type == "number":
            argument = tracker.number(float(argument))
        environment[parameter.name] = argument
    try:
        _statements(function.body, environment, tracker)
    except _Returned as returned:
        return Evaluation(returned.value, tracker.widest, tracker.all_numbers_finite)
    raise RouteError("FUNCTION_FELL_THROUGH_WITHOUT_RETURNING")


def evaluate_ir(ir: SemanticIR, name: str, arguments: list[Any]) -> Evaluation:
    for function in ir.functions:
        if function.name == name:
            return evaluate(function, arguments)
    raise RouteError(f"UNKNOWN_FUNCTION:{name}")
