"""2026-08-26 fixes: three front-end gaps in the Python analyzer.

All three are DEFECTS by the repository's own criterion -- a refusal with no
stated reason, or a refusal of something the IR already represents -- not
profile boundaries. None of them widens the certified subset: every one of
them lifts source into IR the subset already contains.

FIX A  `a and b and c` was refused while `(a and b) and c` was accepted.
       Python's parser flattens n-ary boolean operators, so the two spellings
       differ only in how the parser grouped them. `len(node.values) == 2`
       carried no justification. Left-folding reproduces Python's own
       left-to-right grouping exactly, and canonical `&&`/`||` short-circuit
       (canonical.py `_expression`), so the folded form short-circuits the
       same way.

FIX B  No negative literal could be lifted at all. Python spells `-1` as
       `UnaryOp(USub, Constant(1))`, so `return -1`, `x + -1` and
       `-9223372036854775808` were all `PYTHON_UNSUPPORTED_EXPRESSION:UnaryOp`.
       The IR has always represented negative literals -- emitter.py carries
       per-target compensations for exactly this value in Kotlin, PHP, C++ and
       Objective-C ("there is no negative literal in C or C++") -- so the
       target side has been carrying detailed support for a constant the
       source side could never produce. Folding the sign into the literal is
       pure syntax.

       Unary minus on an EXPRESSION is a different question and stays refused,
       now with a reason rather than a generic code: lowering `-x` to `0 - x`
       is exact for `integer` but not for `number`, because IEEE-754 gives
       `-(0.0) == -0.0` and `0.0 - 0.0 == +0.0`, and the sign of zero is
       observable in a returned value. Doing it properly needs a real unary
       node in the IR, canonical.py and 13 emitters; it is not free, so it is
       not smuggled in here.

FIX C  `not x` was refused. For a canonical `boolean` it is exactly
       `x == False`, which the IR, the type checker, canonical.py and the z3
       denotation all already handle. A non-boolean operand is Python
       truthiness, which is outside the subset, and still fails closed -- as
       an operand-type mismatch naming `==`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PA = "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py"


def patch(relative: str, old: str, new: str, *, expect: int = 1) -> None:
    path = ROOT / relative
    src = path.read_text(encoding="utf-8")
    found = src.count(old)
    if found != expect:
        raise SystemExit(f"ABORT {relative}: expected {expect} match(es), found {found}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {relative}")


# ---------------------------------------------------------------- FIX B ----
# The signed-literal folder, placed just above `_expression`.
patch(
    PA,
    '''def _expression(node: ast.expr, *, emitted_target: bool = False) -> dict[str, Any]:
    if isinstance(node, ast.Name):
        return {"kind": "name", "value": node.id}''',
    '''def _signed_literal(node: ast.expr) -> ast.Constant | None:
    """`-1` is not a literal in Python's grammar -- it is unary minus applied
    to `1`. Fold the sign back in.

    This is the ONLY unary form lifted here, and it is pure syntax: the result
    is the literal the source obviously means. `bool` is excluded because it is
    an `int` subclass in Python and `-True` is not a boolean.
    """

    if not isinstance(node, ast.UnaryOp) or not isinstance(node.op, ast.USub | ast.UAdd):
        return None
    operand = node.operand
    if not isinstance(operand, ast.Constant):
        return None
    value = operand.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return ast.Constant(value=-value if isinstance(node.op, ast.USub) else +value)


def _expression(node: ast.expr, *, emitted_target: bool = False) -> dict[str, Any]:
    folded = _signed_literal(node)
    if folded is not None:
        node = folded
    if isinstance(node, ast.Name):
        return {"kind": "name", "value": node.id}''',
)

# ------------------------------------------------------------ FIX A + C ----
patch(
    PA,
    '''    if isinstance(node, ast.BoolOp) and len(node.values) == 2:
        return {
            "kind": "binary",
            "operator": "&&" if isinstance(node.op, ast.And) else "||",
            "left": _expression(node.values[0], emitted_target=emitted_target),
            "right": _expression(node.values[1], emitted_target=emitted_target),
        }''',
    '''    if isinstance(node, ast.BoolOp) and len(node.values) >= 2:
        # Python's parser FLATTENS `a and b and c` into one three-value node,
        # so accepting only `len(values) == 2` refused a spelling while
        # accepting `(a and b) and c`, which is the same program. Left-folding
        # reproduces Python's own left-to-right grouping, and produces IR
        # byte-identical to the parenthesized form (see the test).
        #
        # Short-circuiting survives the fold: canonical `&&`/`||` short-circuit
        # (canonical.py `_expression`), so `(a && b) && c` stops exactly where
        # `a and b and c` stops.
        operator = "&&" if isinstance(node.op, ast.And) else "||"
        folded = _expression(node.values[0], emitted_target=emitted_target)
        for value in node.values[1:]:
            folded = {
                "kind": "binary",
                "operator": operator,
                "left": folded,
                "right": _expression(value, emitted_target=emitted_target),
            }
        return folded
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        # `not x` on a canonical boolean IS `x == False`. Nothing new enters
        # the IR, the type checker, canonical.py or the z3 denotation.
        #
        # A non-boolean operand is Python truthiness -- `not ""`, `not 0`,
        # `not []` -- which has no canonical meaning and no agreed spelling
        # across the targets. It still fails closed, as
        # `OPERAND_TYPE_MISMATCH:==:<type>:boolean` from `types.infer`.
        return {
            "kind": "binary",
            "operator": "==",
            "left": _expression(node.operand, emitted_target=emitted_target),
            "right": {"kind": "literal", "value": False},
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        # A signed LITERAL was folded at the top of this function; reaching
        # here means the operand is an expression.
        #
        # Refused with a reason rather than the generic code: lowering `-x` to
        # `0 - x` is exact for `integer` but NOT for `number`, because
        # IEEE-754 makes `-(0.0)` negative zero while `0.0 - 0.0` is positive
        # zero, and the sign of a returned zero is observable. Supporting it
        # honestly needs a unary node in the IR, in canonical.py, in the z3
        # denotation and in all 13 emitters.
        raise RouteError("PYTHON_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET")''',
)

print("2026-08-26 analyzer fixes applied (A: n-ary boolean, B: signed literal, C: not)")
