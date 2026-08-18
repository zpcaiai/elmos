"""Bounded formal proof of the L0 integer arithmetic compensation table.

This is the one layer of the verification stack that answers "for *every*
input" rather than "for the inputs we tried". It is applicable exactly because
the `typed-pure-function-v1` subset is closed, total and finite-width: 64-bit
integer arithmetic over `+ - * / %` is decidable in the theory of bitvectors,
so a solver can discharge each obligation outright.

WHAT IS PROVED
--------------
For each target language L and operator op, that the *emitted compensated
form* denotes the same partial function as the canonical rule:

    forall a, b in int64 .
        canonical(op, a, b) errors  <->  emitted_L(op, a, b) errors
        and, when neither errors, the two values are equal

`canonical` is the exact mathematical result, an error when it leaves
[-2^63, 2^63-1] (rule R1) or when a divisor is zero (rule R2), with `/`
truncating toward zero and `%` taking the sign of the dividend.

HOW STRONG EACH OBLIGATION IS
-----------------------------
Not every line of the report means the same thing, and the differences matter
more than the total:

* THEOREM (go, python) -- the real content. These targets are compensated by
  hand-written helper bodies: ordinary code that can be wrong, transcribed
  into a model and discharged by the solver. `MODELLED_SOURCES` pins each
  transcription to the emitter text it describes, so the model cannot drift
  away from the code it is supposed to be about.
* GUARD_ABSTRACTION (typescript) -- conditional evidence only. The model
  substitutes the canonical error/value into an abstract safe-integer guard;
  it does not encode IEEE-754 arithmetic, `Number.isSafeInteger`, or the real
  emitted expression/helper transcription. UNSAT is therefore reported only
  as PROVED_UNDER_ASSUMPTIONS and never counted as an unconditional proof.
* AXIOM (java, csharp, rust, swift, cpp, objc) -- not proved at all. Their
  compensation *is* a language primitive specified to have the canonical
  behaviour: Math.addExact, checked(), checked_add, Swift's trapping
  operators, __builtin_*_overflow. The obligation is a citation, not something
  a solver can settle. They are covered by differential execution instead.
* BOUNDED -- discharged at narrower widths but not at 64. Bitvector multiply
  paired with bitvector division defeats the budget at full width. This is
  evidence, not proof, and is reported separately for that reason.

Nothing here says anything about any construct outside L0 -- no loops, no
calls, no aggregates. The proof's scope is exactly the subset the route packs
declare, and the subset is small enough for a solver precisely because it is
small enough to be nearly useless on real code. That is the honest reading:
this proves the floor is sound, not that the building exists.

Run directly, or through `tests/test_arithmetic_proof.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import z3  # type: ignore[import-untyped]

WIDTH = 64
WIDE = 128  # exactly enough for the product of two 64-bit values

INT_MIN = -(2**63)
INT_MAX = 2**63 - 1
SAFE_MAX = 2**53 - 1

OPERATORS = ("+", "-", "*", "/", "%")

PROOF_STATUSES = (
    "PROVED",
    "PROVED_UNDER_ASSUMPTIONS",
    "BOUNDED",
    "AXIOM",
    "UNKNOWN",
    "TIMEOUT",
    "COUNTEREXAMPLE",
    "NOT_RUN",
)

#: Widths the campaign attempts, **64 first**. Every model here is written
#: in terms of WIDTH rather than a literal 64, and the canonical rules are
#: width-generic, so the same obligation can be posed at any width.
#:
#: This matters because two of the obligations -- Go's multiplication guard and
#: Python's remainder -- pair a bitvector multiply with a bitvector division,
#: and the solver does not decide those at 64 bits in any practical budget.
#: Discharging them at 8, 16 and 24 bits is *not* a proof at 64: it is bounded
#: verification, and it is reported as such. A property that holds at every
#: narrow width and is stated by width-generic code is good evidence, and it is
#: strictly more than the differential tests alone can say -- but a
#: width-specific counterexample at 64 bits would still be missed, so the
#: 64-bit obligation stays on the ledger as unresolved rather than being
#: quietly counted as discharged.
#:
#: The order is not cosmetic. A z3 process that has already spent several
#: timed-out queries decides later ones far more slowly, so asking narrow
#: widths first made the 64-bit obligation *look* undecidable: `python /`
#: discharges in 2.4s from a clean process and times out when it follows four
#: exhausted queries. Asking the width that matters first avoids that.
LADDER_WIDTHS = (64, 32, 24, 16, 8)


@contextmanager
def at_width(width: int) -> Iterator[None]:
    """Pose the obligations at `width` bits instead of 64."""
    global WIDTH, WIDE, INT_MIN, INT_MAX
    previous = (WIDTH, WIDE, INT_MIN, INT_MAX)
    WIDTH, WIDE = width, width * 2
    INT_MIN, INT_MAX = -(2 ** (width - 1)), 2 ** (width - 1) - 1
    try:
        yield
    finally:
        WIDTH, WIDE, INT_MIN, INT_MAX = previous


@dataclass(frozen=True)
class Obligation:
    target: str
    operator: str
    kind: str  # "THEOREM", "GUARD_ABSTRACTION", or "AXIOM"
    detail: str


@dataclass(frozen=True)
class Result:
    obligation: Obligation
    status: str
    counterexample: str | None = None
    solver_inputs: tuple[dict[str, object], ...] = ()
    assumptions: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Canonical semantics, in exact arithmetic
# --------------------------------------------------------------------------


def _wide(value: z3.BitVecRef) -> z3.BitVecRef:
    return z3.SignExt(WIDE - WIDTH, value)


def _in_range(wide: z3.BitVecRef) -> z3.BoolRef:
    return z3.And(wide >= z3.BitVecVal(INT_MIN, WIDE), wide <= z3.BitVecVal(INT_MAX, WIDE))


def _division_error(a: z3.BitVecRef, b: z3.BitVecRef) -> z3.BoolRef:
    """R2, plus the one carve-out the rule makes beyond "result out of range".

    INT64_MIN % -1 is mathematically 0 and would fit, but C# raises
    OverflowException and Rust's checked_rem returns None for it. Declaring it
    an error is what lets all nine targets agree, and it is the behaviour the
    differential corpus already records.
    """
    return z3.Or(b == 0, z3.And(a == z3.BitVecVal(INT_MIN, WIDTH), b == z3.BitVecVal(-1, WIDTH)))


def _safe_divisor(b: z3.BitVecRef) -> z3.BitVecRef:
    """Keep the solver away from the undefined point without weakening the
    claim: every formula using this is guarded by `_division_error`."""
    return z3.If(b == 0, z3.BitVecVal(1, WIDTH), b)


def _no_overflow(operator: str, a: z3.BitVecRef, b: z3.BitVecRef) -> z3.BoolRef:
    """Whether the exact result of a signed 64-bit `op` fits in 64 bits.

    Stated with z3's native overflow predicates rather than by computing the
    result in a wider sort and range-checking it. The two say the same thing,
    but the wide encoding makes the solver reason about a 128-bit multiply,
    which it does not decide in any practical time; the native predicates it
    handles directly.
    """
    if operator == "+":
        return z3.And(z3.BVAddNoOverflow(a, b, signed=True), z3.BVAddNoUnderflow(a, b))
    if operator == "-":
        return z3.And(z3.BVSubNoOverflow(a, b), z3.BVSubNoUnderflow(a, b, signed=True))
    if operator == "*":
        return z3.And(z3.BVMulNoOverflow(a, b, signed=True), z3.BVMulNoUnderflow(a, b))
    raise ValueError(operator)  # pragma: no cover


def canonical(operator: str, a: z3.BitVecRef, b: z3.BitVecRef) -> tuple[z3.BoolRef, z3.BitVecRef]:
    """(errors, value) for the canonical rule, entirely in the 64-bit sort.

    Every non-error result fits in 64 bits by definition -- that is what R1
    says -- so the only thing a wider sort would buy is a way to *ask* whether
    it fits, and `_no_overflow` answers that directly. When there is no
    overflow the wrapped 64-bit result equals the exact one, so the value
    below is exact wherever it is defined.
    """
    if operator in {"/", "%"}:
        divisor = _safe_divisor(b)
        # bvsdiv truncates toward zero and bvsrem takes the sign of the
        # dividend, which is exactly the canonical pair.
        return _division_error(a, b), (a / divisor if operator == "/" else z3.SRem(a, divisor))
    value = {"+": a + b, "-": a - b, "*": a * b}[operator]
    return z3.Not(_no_overflow(operator, a, b)), value


# --------------------------------------------------------------------------
# Target models. Each returns (errors, value-as-wide-bitvector).
#
# The models transcribe the *emitted* source, not an idealisation of it: the
# Go and Python entries below are line-by-line readings of the helper bodies
# in emitter.py, which is what makes their proof worth running.
# --------------------------------------------------------------------------

Model = Callable[[z3.BitVecRef, z3.BitVecRef], tuple[z3.BoolRef, z3.BitVecRef]]


def go_model(operator: str) -> Model:
    """func elmosChecked{Add,Sub,Mul,Div,Mod} in emitter.py's _GO_HELPERS."""

    def model(a: z3.BitVecRef, b: z3.BitVecRef) -> tuple[z3.BoolRef, z3.BitVecRef]:
        minimum = z3.BitVecVal(INT_MIN, WIDTH)
        if operator == "+":
            # sum := left + right   (Go's + wraps)
            # if (right > 0 && sum < left) || (right < 0 && sum > left) { panic }
            total = a + b
            errors = z3.Or(z3.And(b > 0, total < a), z3.And(b < 0, total > a))
            return errors, total
        if operator == "-":
            difference = a - b
            errors = z3.Or(z3.And(b < 0, difference < a), z3.And(b > 0, difference > a))
            return errors, difference
        if operator == "*":
            # if left == 0 || right == 0 { return 0 }
            # if (left == -1 && right == min) || (right == -1 && left == min) { panic }
            # product := left * right
            # if product/right != left { panic }
            zero = z3.Or(a == 0, b == 0)
            explicit = z3.Or(z3.And(a == -1, b == minimum), z3.And(b == -1, a == minimum))
            product = a * b
            # Go's / is truncating signed division; the guard only runs when
            # right != 0, which `zero` has already short-circuited.
            round_trip = z3.If(b == 0, z3.BoolVal(False), product / b != a)
            errors = z3.And(z3.Not(zero), z3.Or(explicit, round_trip))
            return errors, z3.If(zero, z3.BitVecVal(0, WIDTH), product)
        if operator in {"/", "%"}:
            # if right == 0 { panic }
            # if left == elmosIntegerMin && right == -1 { panic }
            errors = z3.Or(b == 0, z3.And(a == minimum, b == -1))
            divisor = _safe_divisor(b)
            return errors, (a / divisor if operator == "/" else z3.SRem(a, divisor))
        raise ValueError(operator)  # pragma: no cover

    return model


def python_model(operator: str) -> Model:
    """_elmos_checked_*, _elmos_truncating_div/mod and _elmos_in_range.

    Python's int is unbounded, so the helper body computes exactly and only
    `_elmos_in_range` narrows. Modelling that needs no wider sort: "the exact
    result does not fit" is `_no_overflow`, and wherever it does fit the
    wrapped 64-bit value is the exact one.

    The division helper takes abs() of both operands *in unbounded integers*,
    so abs(INT64_MIN) is 2^63 -- one past what 64 signed bits hold. The 64-bit
    negation of INT64_MIN is its own bit pattern, and read as *unsigned* that
    pattern is exactly 2^63, so an unsigned division over the same bits
    reproduces the helper for every input including that one.
    """

    def model(a: z3.BitVecRef, b: z3.BitVecRef) -> tuple[z3.BoolRef, z3.BitVecRef]:
        if operator in {"+", "-", "*"}:
            value = {"+": a + b, "-": a - b, "*": a * b}[operator]
            return z3.Not(_no_overflow(operator, a, b)), value
        if operator == "/":
            # if right == 0: raise
            # quotient = abs(left) // abs(right)
            # return _elmos_in_range(quotient if (left >= 0) == (right >= 0) else -quotient)
            absolute_a = z3.If(a >= 0, a, -a)
            absolute_b = z3.If(b >= 0, b, -b)
            divisor = z3.If(b == 0, z3.BitVecVal(1, WIDTH), absolute_b)
            quotient = z3.UDiv(absolute_a, divisor)
            same_sign = (a >= 0) == (b >= 0)
            signed = z3.If(same_sign, quotient, -quotient)
            # |a| // |b| never exceeds 2^63, so the only way the signed result
            # leaves the range is a positive quotient above INT64_MAX -- which
            # is exactly INT64_MIN / -1.
            out_of_range = z3.And(same_sign, z3.UGT(quotient, z3.BitVecVal(INT_MAX, WIDTH)))
            return z3.Or(b == 0, out_of_range), signed
        if operator == "%":
            # return left - _elmos_truncating_div(left, right) * right
            division_errors, quotient = python_model("/")(a, b)
            return division_errors, a - quotient * b
        raise ValueError(operator)  # pragma: no cover

    return model


def exact_error_model(operator: str) -> Model:
    """Targets whose primitive is specified to fail exactly on the canonical
    error set: Java's Math.*Exact, C#'s checked(), Rust's checked_*, Swift's
    trapping operators and Clang/GCC's __builtin_*_overflow."""

    def model(a: z3.BitVecRef, b: z3.BitVecRef) -> tuple[z3.BoolRef, z3.BitVecRef]:
        return canonical(operator, a, b)

    return model


# --------------------------------------------------------------------------
# TypeScript: the safe-integer restriction
#
# A TypeScript `number` is IEEE-754 binary64, which represents every integer up
# to 2^53-1 exactly and only some beyond. The emitted code guards every
# integer operand and every integer result with Number.isSafeInteger, so the
# domain where TypeScript *succeeds* is exactly the domain where its
# arithmetic is exact -- and on that domain the floating-point operations
# coincide with the integer ones. That is what makes the obligation statable
# in bitvectors rather than the floating-point theory: inside the guard there
# is no rounding to reason about.
#
# The obligation, for all a, b that are safe integers:
#     canonical defined and its result safe  ->  TypeScript returns it exactly
#     otherwise                              ->  TypeScript fails
#
# RESIDUAL, recorded rather than proved: whether an f64 result that is *not*
# exact could round onto a value Number.isSafeInteger accepts, letting
# TypeScript return a wrong number instead of failing. It cannot for `+` and
# `-`: two safe integers sum to at most 2^54-2 in magnitude, integers above
# 2^53 are representable only when even, and a rounded odd sum stays above
# 2^53 and so stays unsafe. For `*` the same argument needs the full
# floating-point theory, and it is the differential sweep -- 400 compiled and
# executed comparisons across five toolchains -- that covers it today.
# --------------------------------------------------------------------------

TYPESCRIPT_GUARD_ABSTRACTION_ASSUMPTIONS = (
    "UNMODELED:IEEE-754-binary64-arithmetic-rounding-and-special-values",
    "UNMODELED:Number.isSafeInteger-runtime-semantics",
    "UNMODELED:Math.trunc-and-TypeScript-remainder-runtime-semantics",
    "UNMODELED:real-emitted-expression-and-helper-transcription",
    "ASSUMED:pinned-TypeScript-compiler-and-Node-runtime-conformance",
)


def _is_safe(value: z3.BitVecRef) -> z3.BoolRef:
    return z3.And(value >= z3.BitVecVal(-SAFE_MAX, WIDTH), value <= z3.BitVecVal(SAFE_MAX, WIDTH))


def typescript_model(operator: str) -> Model:
    """A guard abstraction, not a transcription of emitted TypeScript.

    The canonical error and value are deliberately reused below. Consequently
    this model can establish only that the abstract guard predicate is
    internally consistent. The assumptions above retain every missing bridge
    to actual JavaScript/TypeScript execution.
    """

    def model(a: z3.BitVecRef, b: z3.BitVecRef) -> tuple[z3.BoolRef, z3.BitVecRef]:
        canonical_errors, canonical_value = canonical(operator, a, b)
        # _elmosRequireNonZero on the divisor, then _elmosRequireSafeInteger on
        # both operands and on the result.
        errors = z3.Or(
            canonical_errors,
            z3.Not(_is_safe(a)),
            z3.Not(_is_safe(b)),
            z3.Not(_is_safe(canonical_value)),
        )
        return errors, canonical_value

    return model


def typescript_restriction(a: z3.BitVecRef, b: z3.BitVecRef) -> z3.BoolRef:
    """The domain the TypeScript obligation is posed on."""
    return z3.And(_is_safe(a), _is_safe(b))


# --------------------------------------------------------------------------
# Discharge
# --------------------------------------------------------------------------

#: Targets whose compensation is a language primitive, with the citation that
#: stands in for a proof.
_AXIOMATISED = {
    "java": (
        "Math.addExact/subtractExact/multiplyExact throw ArithmeticException exactly "
        "on int64 overflow (JLS 15.18, java.lang.Math)"
    ),
    "csharp": (
        "checked() raises OverflowException exactly on int64 overflow; / and % raise "
        "DivideByZeroException on 0 and OverflowException on MinValue/-1 (ECMA-334 12.8.3)"
    ),
    "rust": (
        "i64::checked_add/sub/mul/div/rem return None exactly on overflow and on a zero divisor (std::primitive::i64)"
    ),
    "swift": (
        "Int arithmetic operators trap on overflow; / and % trap on 0 and on Int.min / -1 "
        "(Swift Programming Language, Advanced Operators)"
    ),
    "cpp": (
        "__builtin_add_overflow/sub/mul report exactly the mathematical overflow; the zero "
        "and INT64_MIN/-1 guards are explicit in the helper"
    ),
    "objc": "same __builtin_*_overflow contract as C++, with NSException as the failure mode",
}

_PROVEN_MODELS: dict[str, Callable[[str], Model]] = {
    "go": go_model,
    "python": python_model,
}


#: Sign quadrants. Posing an obligation once per quadrant is what makes the
#: division obligations tractable: `python /` goes from a timeout to under
#: three seconds, because each case collapses the abs()/negate pair into a
#: direct identity. The disjunction of the cases is the whole domain, so the
#: split weakens nothing.
def _sign_splits(a: z3.BitVecRef, b: z3.BitVecRef) -> list[tuple[str, z3.BoolRef]]:
    return [
        ("b == 0", b == 0),
        ("a >= 0, b > 0", z3.And(a >= 0, b > 0)),
        ("a >= 0, b < 0", z3.And(a >= 0, b < 0)),
        ("a < 0, b > 0", z3.And(a < 0, b > 0)),
        ("a < 0, b < 0", z3.And(a < 0, b < 0)),
    ]


def _timeout_ms() -> int:
    return int(os.environ.get("ELMOS_PROOF_TIMEOUT_MS", "20000"))


def _configure_solver(solver: z3.Solver) -> None:
    solver.set("timeout", _timeout_ms())
    solver.set("random_seed", 0)
    solver.set("smt.random_seed", 0)


def _theorem_queries(
    operator: str, model: Model, *, split: bool = True
) -> list[tuple[str, z3.Solver, z3.BitVecRef, z3.BitVecRef]]:
    a = z3.BitVec("a", WIDTH)
    b = z3.BitVec("b", WIDTH)
    canonical_errors, canonical_value = canonical(operator, a, b)
    target_errors, target_value = model(a, b)
    claim = z3.And(
        canonical_errors == target_errors,
        z3.Implies(z3.Not(canonical_errors), canonical_value == target_value),
    )
    cases = _sign_splits(a, b) if split else [("all inputs", z3.BoolVal(True))]
    queries = []
    for label, assumption in cases:
        solver = z3.Solver()
        _configure_solver(solver)
        solver.add(assumption)
        solver.add(z3.Not(claim))
        queries.append((label, solver, a, b))
    return queries


def _prove(operator: str, model: Model, *, split: bool = True) -> Result | None:
    """None when the obligation is discharged, otherwise the failure."""
    for label, solver, a, b in _theorem_queries(operator, model, split=split):
        verdict = solver.check()
        if verdict == z3.unsat:
            continue
        if verdict == z3.unknown:
            reason = solver.reason_unknown()
            status = "TIMEOUT" if "timeout" in reason.lower() else "UNKNOWN"
            return Result(
                Obligation("", operator, "THEOREM", label),
                status,
                f"case {label}: {reason}",
            )
        values = solver.model()
        return Result(
            Obligation("", operator, "THEOREM", label),
            "COUNTEREXAMPLE",
            f"a={values.eval(a).as_signed_long()} b={values.eval(b).as_signed_long()} ({label})",
        )
    return None


def prove_on_ladder(operator: str, factory: Callable[[str], Model]) -> tuple[str, str]:
    """Discharge an obligation at the widest width the budget allows.

    Returns (status, detail). PROVED means the 64-bit obligation itself was
    discharged; BOUNDED means every narrower width was, and 64 was not.
    """
    discharged: list[int] = []
    for width in LADDER_WIDTHS:
        with at_width(width):
            failure = _prove(operator, factory(operator))
        if failure is None:
            discharged.append(width)
            if width == WIDTH:
                # The obligation that matters is discharged; the narrower
                # widths would only be corroboration.
                return "PROVED", ""
            continue
        if failure.status == "COUNTEREXAMPLE":
            return "COUNTEREXAMPLE", f"at {width} bits: {failure.counterexample}"
        # Do not stop at the first timeout. Bitvector decision cost is not
        # monotonic in width -- `python /` times out at 24 bits and discharges
        # at 64 -- so a break here would under-report what was actually proved.
    if WIDTH in discharged:
        return "PROVED", ""
    if discharged:
        return "BOUNDED", "verified at " + ", ".join(f"{w}" for w in discharged) + " bits, not at 64"
    return "UNKNOWN", "no width discharged within the budget"


# --------------------------------------------------------------------------
# Keeping the models honest
#
# Every model above is a hand transcription of a helper body in emitter.py. A
# proof about a transcription says nothing about the code unless the two are
# known to agree, and nothing in a solver run can notice if they drift apart:
# a mutation campaign confirmed exactly that, breaking all four Go overflow
# guards without a single proof failing.
#
# So the transcription is pinned. `MODELLED_SOURCES` names, for each model,
# the emitter helper it claims to describe, and `check_transcriptions` fails
# when one of them has changed since the model was written. Changing an
# emitted helper is then a two-part edit -- the code and the model that
# describes it -- rather than a silent divergence.
# --------------------------------------------------------------------------

#: (target, operator) -> (helper registry name, helper key). The registry is
#: read from emitter.py at call time, so this stays a live comparison.
MODELLED_SOURCES: dict[tuple[str, str], tuple[str, str]] = {
    ("go", "+"): ("_GO_HELPERS", "checked_add"),
    ("go", "-"): ("_GO_HELPERS", "checked_sub"),
    ("go", "*"): ("_GO_HELPERS", "checked_mul"),
    ("go", "/"): ("_GO_HELPERS", "checked_div"),
    ("go", "%"): ("_GO_HELPERS", "checked_mod"),
    ("python", "+"): ("_PYTHON_HELPERS", "checked_add"),
    ("python", "-"): ("_PYTHON_HELPERS", "checked_sub"),
    ("python", "*"): ("_PYTHON_HELPERS", "checked_mul"),
    ("python", "/"): ("_PYTHON_HELPERS", "truncating_div"),
    ("python", "%"): ("_PYTHON_HELPERS", "truncating_mod"),
    # These pins detect helper byte drift only. They do not establish that the
    # guard abstraction below is a faithful semantic transcription of either
    # helper, which remains an explicit conditional assumption.
    ("typescript", "safe-integer-guard"): ("_TYPESCRIPT_HELPERS", "safe_integer"),
    ("typescript", "non-zero-guard"): ("_TYPESCRIPT_HELPERS", "non_zero"),
}

#: sha256 of each pinned helper at the revision these models were written
#: against. Refresh with `--refresh-pins` after deliberately changing a helper
#: *and* re-reading the model that describes it.
#:
#: 2026-08: `typescript safe-integer-guard` was refreshed after the guard began
#: normalising negative zero -- `return value` became
#: `return Object.is(value, -0) ? 0 : value`. Re-read against the model below:
#: the abstraction is over `WIDTH`-bit bitvectors, where -0 and 0 are the same
#: value, so the normalisation is the identity there and the claim is unchanged.
#: The throw path was not touched. The change itself is a real cross-language
#: fix: TypeScript numbers are binary64, so without it an integer result of -0
#: would come back distinguishable by `Object.is` from the 0 every other target
#: returns.
TRANSCRIPTION_PINS: dict[str, str] = {
    "go %": "59507207ed70cac383b01ad802786a85dbc126af4604e7dbbaea80ccccaec7c9",
    "go *": "a864744ea2cc8d0a13cc95b87adaa9fe579a3408d3de97144ecc7ffff652eac2",
    "go +": "c52af231c25d37b98c1e80c8043d794a564b750f56e8dcf7891beca3c2c50355",
    "go -": "59e5c5a0b8ad1cd7b4d67bf61d418bfb287b655455cc04deda8256fb98519a89",
    "go /": "db3e74e70068fa79730dad2af064bdc5bbaa03c16660377cd2c3549c615dc497",
    "python %": "84476b34dc854b542e9d3efb465d076a669c72913103715812a80b7d97cd37df",
    "python *": "c02f1f10a5b9de84ad751171111bbaabcb4faf93a3e3ceb370a602bdb0771652",
    "python +": "e8aaacaaea26eda14d941efab2be86e39dea994d7a9f30495487b498c1d0602d",
    "python -": "9757259d192830cae6c6bb0addda87e6c02ff59bec207e1ed214374ca4e9228f",
    "python /": "8435959b659dc584f26cd1e5beeb5147714e55535dc6d1240b9502b5341a3051",
    "typescript non-zero-guard": "f6e5d24769f7b8095bdb8024b90b7a93e306c801f2810a882e46c3085781f975",
    "typescript safe-integer-guard": "9351765360a6c33269345e82a91178dae93024cc3a81133b46ca22eb5b70413c",
}


def _helper_source(registry_name: str, key: str) -> str:
    from elmos_polyglot_route import emitter  # type: ignore[import-untyped]

    return cast(str, getattr(emitter, registry_name)[key])


def transcription_digests() -> dict[str, str]:
    import hashlib

    digests: dict[str, str] = {}
    for (target, operator), (registry_name, key) in sorted(MODELLED_SOURCES.items()):
        source = _helper_source(registry_name, key)
        digests[f"{target} {operator}"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return digests


def check_transcriptions() -> list[str]:
    """Names of models whose emitted helper no longer matches its pin."""
    if not TRANSCRIPTION_PINS:
        return []
    current = transcription_digests()
    stale = [name for name, digest in TRANSCRIPTION_PINS.items() if current.get(name) != digest]
    unpinned = [name for name in current if name not in TRANSCRIPTION_PINS]
    return sorted(stale) + sorted(unpinned)


def _typescript_query(operator: str) -> tuple[z3.Solver, z3.BitVecRef, z3.BitVecRef]:
    a = z3.BitVec("a", WIDTH)
    b = z3.BitVec("b", WIDTH)
    canonical_errors, canonical_value = canonical(operator, a, b)
    target_errors, target_value = typescript_model(operator)(a, b)
    claim = z3.Implies(
        typescript_restriction(a, b),
        z3.And(
            z3.Implies(
                z3.And(z3.Not(canonical_errors), _is_safe(canonical_value)),
                z3.And(z3.Not(target_errors), target_value == canonical_value),
            ),
            z3.Implies(z3.Or(canonical_errors, z3.Not(_is_safe(canonical_value))), target_errors),
        ),
    )
    solver = z3.Solver()
    _configure_solver(solver)
    solver.add(z3.Not(claim))
    return solver, a, b


def _typescript_verdict(operator: str) -> tuple[str, str]:
    solver, a, b = _typescript_query(operator)
    verdict = solver.check()
    if verdict == z3.unsat:
        return "PROVED_UNDER_ASSUMPTIONS", ""
    if verdict == z3.unknown:
        reason = solver.reason_unknown()
        status = "TIMEOUT" if "timeout" in reason.lower() else "UNKNOWN"
        return status, reason
    values = solver.model()
    return "COUNTEREXAMPLE", (f"a={values.eval(a).as_signed_long()} b={values.eval(b).as_signed_long()}")


#: Obligations are discharged in a *fresh process* each. z3's decision cost
#: rises sharply in a process that has already exhausted several budgets, and
#: the effect is large enough to change the verdict: `python /` discharges at
#: 64 bits in 2.4s from a clean start and reports BOUNDED when it runs after
#: three timed-out queries. Running them in-process made the campaign's answer
#: depend on the order it happened to ask, which is not a property a proof
#: report should have.
def _solver_formulations(target: str, operator: str) -> tuple[dict[str, object], ...]:
    formulations: list[dict[str, object]] = []
    widths = (64,) if target == "typescript" else LADDER_WIDTHS
    for width in widths:
        with at_width(width):
            if target == "typescript":
                queries = [("safe-integer-domain", *_typescript_query(operator))]
            else:
                queries = [
                    (label, solver, a, b)
                    for label, solver, a, b in _theorem_queries(operator, _PROVEN_MODELS[target](operator))
                ]
        for label, solver, _a, _b in queries:
            smt2 = solver.to_smt2()
            formulations.append(
                {
                    "width": width,
                    "case": label,
                    "sha256": "sha256:" + hashlib.sha256(smt2.encode("utf-8")).hexdigest(),
                    "smt2": smt2,
                    "purpose": (
                        "guard-abstraction replay input; UNSAT is conditional evidence only"
                        if target == "typescript"
                        else "exact replay input; status is taken only from the solver result"
                    ),
                    "assumptions": (list(TYPESCRIPT_GUARD_ABSTRACTION_ASSUMPTIONS) if target == "typescript" else []),
                }
            )
    return tuple(formulations)


def _discharge_isolated(target: str, operator: str) -> tuple[str, str, tuple[dict[str, object], ...]]:
    formulations = _solver_formulations(target, operator)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, this module re-entered
            [sys.executable, __file__, "--obligation", target, operator],
            capture_output=True,
            text=True,
            timeout=1800,
            env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src")},
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "worker exceeded 1800 seconds", formulations
    worker_result = _parse_worker_result(completed.stdout)
    if worker_result is not None:
        # A fail-closed worker intentionally exits non-zero for UNKNOWN,
        # TIMEOUT, COUNTEREXAMPLE, or a caller-selected --fail-on status. Its
        # structured result remains the authoritative solver verdict; the
        # process exit code is policy, not a replacement proof status.
        status, detail = worker_result
        return status, detail, formulations
    diagnostic = completed.stderr.strip()[-200:]
    if completed.returncode != 0:
        return "UNKNOWN", f"worker failed without valid JSON: {diagnostic}", formulations
    return "UNKNOWN", "worker returned no valid proof-result JSON", formulations


def _parse_worker_result(stdout: str) -> tuple[str, str] | None:
    """Decode the final structured worker line without trusting exit status."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    detail = payload.get("detail")
    if status not in PROOF_STATUSES or not isinstance(detail, str):
        return None
    return status, detail


def discharge() -> list[Result]:
    results: list[Result] = []
    for target, citation in sorted(_AXIOMATISED.items()):
        for operator in OPERATORS:
            results.append(Result(Obligation(target, operator, "AXIOM", citation), "AXIOM"))
    for target, _factory in sorted(_PROVEN_MODELS.items()):
        for operator in OPERATORS:
            obligation = Obligation(target, operator, "THEOREM", f"emitted helper body for `{operator}`")
            status, detail, formulations = _discharge_isolated(target, operator)
            results.append(Result(obligation, status, detail or None, formulations))
    for operator in OPERATORS:
        obligation = Obligation(
            "typescript",
            operator,
            "GUARD_ABSTRACTION",
            "abstract safe-integer guard consistency; not an IEEE-754 or helper-transcription theorem",
        )
        status, detail, formulations = _discharge_isolated("typescript", operator)
        results.append(
            Result(
                obligation,
                status,
                detail or None,
                formulations,
                TYPESCRIPT_GUARD_ABSTRACTION_ASSUMPTIONS,
            )
        )
    return results


def _run_one(target: str, operator: str) -> tuple[str, str, bool]:
    """Discharge one obligation and return its verdict plus input validity."""
    supported_targets = {*_PROVEN_MODELS, "typescript"}
    if target not in supported_targets:
        status = "UNKNOWN"
        detail = f"unsupported obligation target: {target!r}"
        valid = False
    elif operator not in OPERATORS:
        status = "UNKNOWN"
        detail = f"unsupported obligation operator: {operator!r}"
        valid = False
    elif target == "typescript":
        status, detail = _typescript_verdict(operator)
        valid = True
    else:
        status, detail = prove_on_ladder(operator, _PROVEN_MODELS[target])
        valid = True
    print(json.dumps({"status": status, "detail": detail}))
    return status, detail, valid


def _obligation_input_digest(result: Result, pins: dict[str, str]) -> str:
    key = f"{result.obligation.target} {result.obligation.operator}"
    relevant_pins = _obligation_transcription_pins(result, pins)
    payload = {
        "canonical_model": "int64-partial-arithmetic-v1",
        "target": result.obligation.target,
        "operator": result.obligation.operator,
        "kind": result.obligation.kind,
        "detail": result.obligation.detail,
        "transcription_digest": pins.get(key),
        "transcription_digests": relevant_pins,
        "widths": [64] if result.obligation.target == "typescript" else list(LADDER_WIDTHS),
        "timeout_ms": _timeout_ms(),
        "solver": {"name": "z3", "version": z3.get_version_string()},
        "solver_inputs": [item["sha256"] for item in result.solver_inputs],
        "assumptions": list(result.assumptions),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _obligation_transcription_pins(
    result: Result,
    pins: dict[str, str],
) -> dict[str, str]:
    if result.obligation.target == "typescript":
        names = ["typescript safe-integer-guard"]
        if result.obligation.operator in {"/", "%"}:
            names.append("typescript non-zero-guard")
        return {name: pins[name] for name in names}
    key = f"{result.obligation.target} {result.obligation.operator}"
    return {key: pins[key]} if key in pins else {}


def _solver_binary_identity() -> dict[str, object]:
    library_directory = Path(z3.__file__).resolve().parent / "lib"
    names = {
        "Darwin": ("libz3.dylib", "libz3.4.16.dylib"),
        "Linux": ("libz3.so",),
        "Windows": ("libz3.dll",),
    }.get(platform.system(), ())
    library = next((library_directory / name for name in names if (library_directory / name).is_file()), None)
    if library is None:
        raise RuntimeError("Z3_NATIVE_LIBRARY_NOT_FOUND")
    content = library.read_bytes()
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    lock_bytes = lock.read_bytes()
    return {
        "filename": library.name,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "lockfile_sha256": "sha256:" + hashlib.sha256(lock_bytes).hexdigest(),
    }


def campaign_payload(results: list[Result]) -> dict[str, object]:
    """Build deterministic evidence; callers must parse status, not exit code alone."""
    pins = transcription_digests()
    obligations: list[dict[str, object]] = []
    for result in results:
        target = result.obligation.target
        operator = result.obligation.operator
        obligations.append(
            {
                "obligation_id": f"int64-{target}-{OPERATORS.index(operator):02d}",
                "target": target,
                "operator": operator,
                "kind": result.obligation.kind,
                "status": result.status,
                "detail": result.obligation.detail,
                "diagnostic": result.counterexample,
                "input_digest": _obligation_input_digest(result, pins),
                "transcription_digest": pins.get(f"{target} {operator}"),
                "transcription_digests": _obligation_transcription_pins(result, pins),
                "solver_inputs": list(result.solver_inputs),
                "assumptions": list(result.assumptions),
                "unconditional_proof": result.status == "PROVED",
                "replay": {
                    "command": (
                        "uv --directory engines/polyglot-route-engine run --locked python "
                        f"tools/prove_arithmetic_compensation.py --obligation {target} {operator}"
                    )
                },
            }
        )
    counts = {status: sum(1 for result in results if result.status == status) for status in PROOF_STATUSES}
    return {
        "schema_version": "1.0.0",
        "campaign_key": "typed-pure-function-v1-int64-arithmetic-compensation",
        "scope": {
            "semantic_profile": "typed-pure-function-v1",
            "constructs": ["binary-arithmetic"],
            "operators": list(OPERATORS),
            "integer_width": 64,
            "explicitly_excluded": [
                "source-analyzer-soundness",
                "control-flow-composition",
                "floating-point-equivalence",
                "Number.isSafeInteger-runtime-semantics",
                "real-TypeScript-helper-transcription",
                "framework-database-io-concurrency",
            ],
        },
        "solver": {
            "name": "z3-solver",
            "version": z3.get_version_string(),
            "python": platform.python_version(),
            "options": {
                "timeout_ms": _timeout_ms(),
                "random_seed": 0,
                "smt_random_seed": 0,
            },
            "width_ladder": list(LADDER_WIDTHS),
            "binary": _solver_binary_identity(),
        },
        "transcription_pins": pins,
        "counts": counts,
        "all_required_proved": all(result.status == "PROVED" for result in results),
        "obligations": obligations,
    }


def _parse_fail_on(value: str) -> set[str]:
    aliases = {
        "proved": "PROVED",
        "proved_under_assumptions": "PROVED_UNDER_ASSUMPTIONS",
        "bounded": "BOUNDED",
        "axiom": "AXIOM",
        "unknown": "UNKNOWN",
        "timeout": "TIMEOUT",
        "counterexample": "COUNTEREXAMPLE",
        "not_run": "NOT_RUN",
    }
    requested: set[str] = set()
    for raw in value.split(","):
        key = raw.strip().lower().replace("-", "_")
        if not key:
            continue
        if key not in aliases:
            raise argparse.ArgumentTypeError(f"unknown proof status in --fail-on: {raw}")
        requested.add(aliases[key])
    return requested


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obligation", nargs=2, metavar=("TARGET", "OPERATOR"))
    parser.add_argument("--refresh-pins", action="store_true")
    parser.add_argument("--output", type=argparse.FileType("w", encoding="utf-8"))
    parser.add_argument("--require-64-bit", action="store_true")
    parser.add_argument(
        "--fail-on",
        default="unknown,timeout,counterexample",
        help="comma-separated statuses that produce a non-zero exit",
    )
    args = parser.parse_args(argv)
    try:
        failing_statuses = _parse_fail_on(args.fail_on)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if args.require_64_bit:
        failing_statuses.update({"BOUNDED", "PROVED_UNDER_ASSUMPTIONS"})
    if args.obligation:
        status, _detail, valid = _run_one(args.obligation[0], args.obligation[1])
        return 1 if not valid or status in failing_statuses else 0
    if args.refresh_pins:
        print(json.dumps(transcription_digests(), indent=4, sort_keys=True))
        return 0
    stale = check_transcriptions()
    if stale:
        print("transcription pins are stale, the models may no longer describe the emitter:")
        for name in stale:
            print(f"  - {name}")
        return 1
    results = discharge()
    payload = campaign_payload(results)
    if args.output:
        json.dump(payload, args.output, ensure_ascii=False, indent=2, sort_keys=True)
        args.output.write("\n")
        args.output.close()
    width = max(len(r.obligation.target) for r in results)
    for result in results:
        marker = {
            "PROVED": "proved  ",
            "PROVED_UNDER_ASSUMPTIONS": "assumed ",
            "AXIOM": "axiom   ",
            "BOUNDED": "bounded ",
            "UNKNOWN": "UNKNOWN ",
            "TIMEOUT": "TIMEOUT ",
            "COUNTEREXAMPLE": "REFUTED ",
        }[result.status]
        line = f"  {marker} {result.obligation.target:<{width}}  {result.obligation.operator}"
        if result.counterexample:
            line += f"   <- {result.counterexample}"
        print(line)
    proved = sum(1 for r in results if r.status == "PROVED")
    conditional = sum(1 for r in results if r.status == "PROVED_UNDER_ASSUMPTIONS")
    axioms = sum(1 for r in results if r.status == "AXIOM")
    bounded = sum(1 for r in results if r.status == "BOUNDED")
    unresolved = [r for r in results if r.status in {"UNKNOWN", "TIMEOUT", "COUNTEREXAMPLE"}]
    print(
        f"\n{proved} proved unconditionally at 64 bits, "
        f"{conditional} proved under assumptions, {bounded} bounded to narrower widths, "
        f"{axioms} axiomatised, {len(unresolved)} unresolved"
    )
    return 1 if any(result.status in failing_statuses for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
