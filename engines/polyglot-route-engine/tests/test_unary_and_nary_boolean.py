"""Three front-end gaps, and the line each one draws.

None of these widens the certified subset. Every one of them lifts source into
IR the subset already contained -- which is what made them defects rather than
boundaries:

  `a and b and c`   was refused while `(a and b) and c` was accepted. Same
                    program; Python's parser just flattens the n-ary form.
  `-1`              could not be lifted at all, while `emitter.py` carries
                    per-target compensations for that exact constant in
                    Kotlin, PHP, C++ and Objective-C. The target side has been
                    supporting a literal the source side could never produce.
  `not x`           is `x == False` for a canonical boolean, and every layer
                    already handles `==`.

What stays out stays out for a stated reason, and each of those has a test too.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from elmos_polyglot_route import canonical, types
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.python_analyzer import analyze_python


def _analyze(tmp_path: Path, source: str, name: str):
    path = tmp_path / "unit.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return analyze_python(path, name)


def _body(ir) -> str:
    return json.dumps(ir.functions[0].to_mapping()["body"], sort_keys=True)


# --------------------------------------------------------------- FIX A ----

def test_flattened_and_parenthesized_boolean_chains_produce_identical_ir(tmp_path: Path) -> None:
    """The strongest available statement: not "both are accepted" but "both
    produce the same bytes". If the fold ever stops matching Python's own
    left-to-right grouping, this fails."""

    flat = _analyze(tmp_path, '''
        def f(a: bool, b: bool, c: bool) -> bool:
            return a and b and c
    ''', "f")
    grouped = _analyze(tmp_path, '''
        def f(a: bool, b: bool, c: bool) -> bool:
            return (a and b) and c
    ''', "f")
    assert _body(flat) == _body(grouped)


def test_the_fold_is_left_associative_not_right(tmp_path: Path) -> None:
    flat = _analyze(tmp_path, '''
        def f(a: bool, b: bool, c: bool) -> bool:
            return a or b or c
    ''', "f")
    right = _analyze(tmp_path, '''
        def f(a: bool, b: bool, c: bool) -> bool:
            return a or (b or c)
    ''', "f")
    assert _body(flat) != _body(right), "a right fold would make these equal"


@pytest.mark.parametrize("arity", [2, 3, 4, 7])
def test_boolean_chains_of_any_arity_are_accepted(tmp_path: Path, arity: int) -> None:
    names = [f"p{index}" for index in range(arity)]
    signature = ", ".join(f"{name}: bool" for name in names)
    ir = _analyze(tmp_path, f'''
        def f({signature}) -> bool:
            return {" and ".join(names)}
    ''', "f")
    types.check(ir)


def test_a_long_chain_still_short_circuits_exactly_where_python_does(tmp_path: Path) -> None:
    """Canonical `&&` short-circuits, so the fold must not turn a guarded
    division into an evaluated one. Floats, because `/` on two integers is
    itself outside the subset (Python true-divides)."""

    ir = _analyze(tmp_path, '''
        def f(guard: bool, other: bool, n: float) -> bool:
            return guard and other and 1.0 / n > 0.0
    ''', "f")
    types.check(ir)
    function = ir.functions[0]
    # guard False -> the divisor is never evaluated, so n == 0 is not an error.
    assert canonical.evaluate(function, [False, True, 0.0]).value is False
    with pytest.raises(canonical.DivideByZero):
        canonical.evaluate(function, [True, True, 0.0])


# --------------------------------------------------------------- FIX B ----

@pytest.mark.parametrize(
    ("source_expression", "expected"),
    [("-1", -1), ("+1", 1), ("-0", 0), ("-2.5", -2.5), ("+2.5", 2.5)],
)
def test_a_signed_literal_is_lifted_as_a_literal(
    tmp_path: Path, source_expression: str, expected: object
) -> None:
    return_type = "float" if isinstance(expected, float) else "int"
    ir = _analyze(tmp_path, f'''
        def f() -> {return_type}:
            return {source_expression}
    ''', "f")
    types.check(ir)
    statement = ir.functions[0].body[0]
    assert statement.expression is not None
    assert statement.expression.kind == "literal"
    assert statement.expression.value == expected


def test_the_most_negative_integer_is_now_expressible(tmp_path: Path) -> None:
    """`emitter.py` has always carried Kotlin/PHP/C++/Objective-C
    compensations for this exact value; until now no Python source could
    produce it."""

    ir = _analyze(tmp_path, '''
        def f() -> int:
            return -9223372036854775808
    ''', "f")
    types.check(ir)
    assert ir.functions[0].body[0].expression.value == types.INTEGER_MIN


def test_a_signed_literal_inside_a_larger_expression(tmp_path: Path) -> None:
    ir = _analyze(tmp_path, '''
        def f(x: int) -> int:
            return x + -1
    ''', "f")
    types.check(ir)
    assert canonical.evaluate(ir.functions[0], [10]).value == 9


def test_negative_zero_keeps_its_sign(tmp_path: Path) -> None:
    """The reason `-x` on an expression is NOT lowered to `0 - x`: the folded
    literal keeps the sign of zero, and `0.0 - 0.0` would not."""

    ir = _analyze(tmp_path, '''
        def f() -> float:
            return -0.0
    ''', "f")
    types.check(ir)
    value = ir.functions[0].body[0].expression.value
    assert value == 0.0
    import math
    assert math.copysign(1.0, value) == -1.0


def test_minus_true_is_not_a_signed_literal(tmp_path: Path) -> None:
    """`bool` is an `int` subclass in Python; `-True` is 
    arithmetic on a boolean, not a literal."""

    with pytest.raises(RouteError) as raised:
        _analyze(tmp_path, '''
            def f() -> int:
                return -True
        ''', "f")
    assert "PYTHON_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET" in str(raised.value)


def test_unary_sign_on_an_expression_is_refused_with_a_reason(tmp_path: Path) -> None:
    """Not the generic `UNSUPPORTED_EXPRESSION:UnaryOp`: the code names what
    was refused, because the honest fix needs a unary node in the IR,
    canonical.py, the z3 denotation and 13 emitters."""

    with pytest.raises(RouteError) as raised:
        _analyze(tmp_path, '''
            def f(x: int) -> int:
                return -x
        ''', "f")
    assert str(raised.value) == "PYTHON_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET"


# --------------------------------------------------------------- FIX C ----

def test_not_on_a_boolean_is_equality_against_false(tmp_path: Path) -> None:
    ir = _analyze(tmp_path, '''
        def f(x: bool) -> bool:
            return not x
    ''', "f")
    types.check(ir)
    expression = ir.functions[0].body[0].expression
    assert expression.operator == "=="
    assert expression.right.kind == "literal"
    assert expression.right.value is False
    assert canonical.evaluate(ir.functions[0], [True]).value is False
    assert canonical.evaluate(ir.functions[0], [False]).value is True


def test_double_negation_still_evaluates(tmp_path: Path) -> None:
    ir = _analyze(tmp_path, '''
        def f(x: bool) -> bool:
            return not (not x)
    ''', "f")
    types.check(ir)
    assert canonical.evaluate(ir.functions[0], [True]).value is True


@pytest.mark.parametrize("declared", ["str", "int", "float"])
def test_python_truthiness_still_fails_closed(tmp_path: Path, declared: str) -> None:
    """`not ""`, `not 0`, `not 0.0` are truthiness, which has no canonical
    meaning. The rewrite must not smuggle it in -- it fails in the type
    checker, and the message names `==`."""

    with pytest.raises(RouteError) as raised:
        _analyze(tmp_path, f'''
            def f(x: {declared}) -> bool:
                return not x
        ''', "f")
    assert "OPERAND_TYPE_MISMATCH:==" in str(raised.value)


def test_not_composes_with_a_folded_chain(tmp_path: Path) -> None:
    ir = _analyze(tmp_path, '''
        def f(a: bool, b: bool, c: bool) -> bool:
            return not a and b and c
    ''', "f")
    types.check(ir)
    function = ir.functions[0]
    assert canonical.evaluate(function, [False, True, True]).value is True
    assert canonical.evaluate(function, [True, True, True]).value is False


# ------------------------------------------------- unchanged boundaries ----

def test_chained_comparison_is_still_refused(tmp_path: Path) -> None:
    """`a < b < c` evaluates `b` once in Python and twice in a naive lowering.
    Out of scope for these fixes, and it must not have drifted in."""

    with pytest.raises(RouteError) as raised:
        _analyze(tmp_path, '''
            def f(a: int, b: int, c: int) -> bool:
                return a < b < c
        ''', "f")
    assert "PYTHON_UNSUPPORTED_EXPRESSION:Compare" in str(raised.value)


def test_bitwise_operators_are_still_refused(tmp_path: Path) -> None:
    with pytest.raises(RouteError) as raised:
        _analyze(tmp_path, '''
            def f(a: int, b: int) -> int:
                return a | b
        ''', "f")
    assert "PYTHON_UNSUPPORTED_EXPRESSION" in str(raised.value)


def test_modulo_is_still_refused_because_python_floors(tmp_path: Path) -> None:
    """Unchanged on purpose: an exact lowering of Python's `%` into canonical
    truncating `%` is `((a % b) + b) % b`, which can raise a spurious integer
    overflow when `|b| > 2^62`. A narrow divergence is not fail-closed."""

    with pytest.raises(RouteError) as raised:
        _analyze(tmp_path, '''
            def f(a: int, b: int) -> int:
                return a % b
        ''', "f")
    assert "PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET" in str(raised.value)
