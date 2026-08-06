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
* THEOREM (typescript) -- weaker. It models the guard *structure* the emitter
  applies rather than a helper body, and shows that structure characterises
  exactly the domain on which a binary64 `number` is exact. Only the two guard
  helpers are pinned.
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

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

import z3

WIDTH = 64
WIDE = 128  # exactly enough for the product of two 64-bit values

INT_MIN = -(2**63)
INT_MAX = 2**63 - 1
SAFE_MAX = 2**53 - 1

OPERATORS = ("+", "-", "*", "/", "%")

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
    kind: str  # "THEOREM" or "AXIOM"
    detail: str


@dataclass(frozen=True)
class Result:
    obligation: Obligation
    status: str  # "PROVED", "AXIOM", "COUNTEREXAMPLE", "UNKNOWN"
    counterexample: str | None = None


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


def _is_safe(value: z3.BitVecRef) -> z3.BoolRef:
    return z3.And(
        value >= z3.BitVecVal(-SAFE_MAX, WIDTH), value <= z3.BitVecVal(SAFE_MAX, WIDTH)
    )


def typescript_model(operator: str) -> Model:
    """The emitted TypeScript, restricted to its exact domain."""

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
    "java": "Math.addExact/subtractExact/multiplyExact throw ArithmeticException exactly on int64 overflow (JLS 15.18, java.lang.Math)",
    "csharp": "checked() raises OverflowException exactly on int64 overflow; / and % raise DivideByZeroException on 0 and OverflowException on MinValue/-1 (ECMA-334 12.8.3)",
    "rust": "i64::checked_add/sub/mul/div/rem return None exactly on overflow and on a zero divisor (std::primitive::i64)",
    "swift": "Int arithmetic operators trap on overflow; / and % trap on 0 and on Int.min / -1 (Swift Programming Language, Advanced Operators)",
    "cpp": "__builtin_add_overflow/sub/mul report exactly the mathematical overflow; the zero and INT64_MIN/-1 guards are explicit in the helper",
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
    import os

    return int(os.environ.get("ELMOS_PROOF_TIMEOUT_MS", "20000"))


def _prove(operator: str, model: Model, *, split: bool = True) -> Result | None:
    """None when the obligation is discharged, otherwise the failure."""
    a = z3.BitVec("a", WIDTH)
    b = z3.BitVec("b", WIDTH)
    canonical_errors, canonical_value = canonical(operator, a, b)
    target_errors, target_value = model(a, b)
    claim = z3.And(
        canonical_errors == target_errors,
        z3.Implies(z3.Not(canonical_errors), canonical_value == target_value),
    )
    cases = _sign_splits(a, b) if split else [("all inputs", z3.BoolVal(True))]
    for label, assumption in cases:
        solver = z3.Solver()
        solver.set("timeout", _timeout_ms())
        solver.add(assumption)
        solver.add(z3.Not(claim))
        verdict = solver.check()
        if verdict == z3.unsat:
            continue
        if verdict == z3.unknown:
            return Result(Obligation("", operator, "THEOREM", label), "UNKNOWN", f"case {label}")
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
    # The TypeScript obligation is weaker than the other two: it models the
    # *guard structure* the emitter applies rather than a helper body, so the
    # pin covers only the two helpers that structure calls into.
    ("typescript", "safe-integer-guard"): ("_TYPESCRIPT_HELPERS", "safe_integer"),
    ("typescript", "non-zero-guard"): ("_TYPESCRIPT_HELPERS", "non_zero"),
}

#: sha256 of each pinned helper at the revision these models were written
#: against. Refresh with `--refresh-pins` after deliberately changing a helper
#: *and* re-reading the model that describes it.
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
    "typescript safe-integer-guard": "d775513b6eb174190bb8793902bb60c0b23474894ea4a1f2840d020c5f004b1c",
}


def _helper_source(registry_name: str, key: str) -> str:
    from elmos_polyglot_route import emitter

    return getattr(emitter, registry_name)[key]


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


def _typescript_verdict(operator: str) -> tuple[str, str]:
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
            z3.Implies(
                z3.Or(canonical_errors, z3.Not(_is_safe(canonical_value))), target_errors
            ),
        ),
    )
    solver = z3.Solver()
    solver.set("timeout", _timeout_ms())
    solver.add(z3.Not(claim))
    verdict = solver.check()
    if verdict == z3.unsat:
        return "PROVED", ""
    if verdict == z3.unknown:
        return "UNKNOWN", "solver budget exhausted"
    values = solver.model()
    return "COUNTEREXAMPLE", (
        f"a={values.eval(a).as_signed_long()} b={values.eval(b).as_signed_long()}"
    )


#: Obligations are discharged in a *fresh process* each. z3's decision cost
#: rises sharply in a process that has already exhausted several budgets, and
#: the effect is large enough to change the verdict: `python /` discharges at
#: 64 bits in 2.4s from a clean start and reports BOUNDED when it runs after
#: three timed-out queries. Running them in-process made the campaign's answer
#: depend on the order it happened to ask, which is not a property a proof
#: report should have.
def _discharge_isolated(target: str, operator: str) -> tuple[str, str]:
    import json as _json
    import os
    import subprocess

    completed = subprocess.run(  # noqa: S603 - fixed argv, this module re-entered
        [sys.executable, __file__, "--obligation", target, operator],
        capture_output=True,
        text=True,
        timeout=1800,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src")},
    )
    if completed.returncode != 0:
        return "UNKNOWN", f"worker failed: {completed.stderr.strip()[-200:]}"
    payload = _json.loads(completed.stdout.strip().splitlines()[-1])
    return payload["status"], payload["detail"]


def discharge() -> list[Result]:
    results: list[Result] = []
    for target, citation in sorted(_AXIOMATISED.items()):
        for operator in OPERATORS:
            results.append(
                Result(Obligation(target, operator, "AXIOM", citation), "AXIOM")
            )
    for target, factory in sorted(_PROVEN_MODELS.items()):
        for operator in OPERATORS:
            obligation = Obligation(
                target, operator, "THEOREM", f"emitted helper body for `{operator}`"
            )
            status, detail = _discharge_isolated(target, operator)
            results.append(Result(obligation, status, detail or None))
    for operator in OPERATORS:
        obligation = Obligation(
            "typescript",
            operator,
            "THEOREM",
            "exact on safe integers, fails closed elsewhere",
        )
        status, detail = _discharge_isolated("typescript", operator)
        results.append(Result(obligation, status, detail or None))
    return results


def _run_one(target: str, operator: str) -> int:
    """Worker entry point: discharge a single obligation and print it as JSON."""
    import json as _json

    if target == "typescript":
        status, detail = _typescript_verdict(operator)
    else:
        status, detail = prove_on_ladder(operator, _PROVEN_MODELS[target])
    print(_json.dumps({"status": status, "detail": detail}))
    return 0


def main() -> int:
    if "--obligation" in sys.argv:
        index = sys.argv.index("--obligation")
        return _run_one(sys.argv[index + 1], sys.argv[index + 2])
    if "--refresh-pins" in sys.argv:
        import json as _json

        print(_json.dumps(transcription_digests(), indent=4, sort_keys=True))
        return 0
    stale = check_transcriptions()
    if stale:
        print("transcription pins are stale, the models may no longer describe the emitter:")
        for name in stale:
            print(f"  - {name}")
        return 1
    results = discharge()
    width = max(len(r.obligation.target) for r in results)
    for result in results:
        marker = {
            "PROVED": "proved  ",
            "AXIOM": "axiom   ",
            "BOUNDED": "bounded ",
            "UNKNOWN": "UNKNOWN ",
            "COUNTEREXAMPLE": "REFUTED ",
        }[result.status]
        line = f"  {marker} {result.obligation.target:<{width}}  {result.obligation.operator}"
        if result.counterexample:
            line += f"   <- {result.counterexample}"
        print(line)
    proved = sum(1 for r in results if r.status == "PROVED")
    axioms = sum(1 for r in results if r.status == "AXIOM")
    bounded = sum(1 for r in results if r.status == "BOUNDED")
    bad = [r for r in results if r.status in {"UNKNOWN", "COUNTEREXAMPLE"}]
    print(
        f"\n{proved} proved at 64 bits, {bounded} bounded to narrower widths, "
        f"{axioms} axiomatised, {len(bad)} unresolved"
    )
    return 1 if any(r.status == "COUNTEREXAMPLE" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
