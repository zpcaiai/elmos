"""The solver obligations, run as tests.

`tools/prove_arithmetic_compensation.py` is the full campaign. This module
runs the subset that discharges in well under a second each, so the proofs sit
in the ordinary test suite rather than in a report nobody re-runs.

Two of them earn their place directly: a mutation campaign found that breaking
the Go overflow predicates left every other test green, because no test in
this suite executes Go. The proof does not need a Go toolchain to notice.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

z3 = pytest.importorskip("z3", reason="z3-solver is required for the proof obligations")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
proof = importlib.import_module("prove_arithmetic_compensation")


#: Obligations that discharge quickly. `go *` and the Python division pair
#: involve a bitvector multiply against a division and are left to the full
#: campaign, which runs them with a much larger budget.
FAST = [
    ("go", "+"),
    ("go", "-"),
    ("go", "/"),
    ("go", "%"),
    ("python", "+"),
    ("python", "-"),
    ("python", "*"),
]

_MODELS = {"go": proof.go_model, "python": proof.python_model}


@pytest.mark.parametrize(("target", "operator"), FAST, ids=[f"{t}{o}" for t, o in FAST])
def test_the_emitted_helper_matches_the_canonical_rule(target: str, operator: str) -> None:
    failure = proof._prove(operator, _MODELS[target](operator))
    if failure is None:
        return
    if failure.status == "UNKNOWN":
        pytest.skip(f"solver budget exhausted for {target} {operator}")
    pytest.fail(f"{target} {operator} is refuted by {failure.counterexample}")


def test_the_canonical_rule_is_not_vacuous() -> None:
    """A canonical model that errored on everything, or on nothing, would make
    every obligation above trivially true. Pin both directions."""
    a = z3.BitVec("a", 64)
    b = z3.BitVec("b", 64)
    for operator in proof.OPERATORS:
        errors, _ = proof.canonical(operator, a, b)
        for target_formula, description in ((errors, "reachable"), (z3.Not(errors), "avoidable")):
            solver = z3.Solver()
            solver.add(target_formula)
            assert solver.check() == z3.sat, f"canonical {operator} errors are never {description}"


def test_the_error_sets_are_the_ones_the_rules_describe() -> None:
    """Spot-check the canonical model against the four points the rules name,
    so a mistake in the encoding cannot quietly satisfy every obligation."""
    minimum = z3.BitVecVal(-(2**63), 64)
    maximum = z3.BitVecVal(2**63 - 1, 64)
    one = z3.BitVecVal(1, 64)
    zero = z3.BitVecVal(0, 64)
    negative_one = z3.BitVecVal(-1, 64)

    def errors(operator: str, left: z3.BitVecRef, right: z3.BitVecRef) -> bool:
        flag, _ = proof.canonical(operator, left, right)
        return bool(z3.simplify(flag))

    assert errors("+", maximum, one), "INT64_MAX + 1 must be an error"
    assert errors("-", minimum, one), "INT64_MIN - 1 must be an error"
    assert errors("/", one, zero), "a zero divisor must be an error"
    assert errors("%", one, zero), "a zero divisor must be an error"
    assert errors("/", minimum, negative_one), "INT64_MIN / -1 must be an error"
    assert errors("%", minimum, negative_one), "INT64_MIN % -1 must be an error"
    assert not errors("+", maximum, zero), "INT64_MAX + 0 must not be an error"
    assert not errors("/", minimum, one), "INT64_MIN / 1 must not be an error"


def test_the_models_still_describe_the_emitter() -> None:
    """A solver run cannot notice when a model drifts from the code it claims
    to transcribe -- a mutation campaign broke all four Go overflow guards
    without any proof failing. The pin is what makes the proofs mean
    something about the emitter rather than about a copy of it.

    A failure here is not necessarily a defect: it means an emitted helper
    changed, and the model in tools/prove_arithmetic_compensation.py has to be
    re-read against it before the pins are refreshed with --refresh-pins.
    """
    stale = proof.check_transcriptions()
    assert not stale, (
        "these emitted helpers no longer match the proof models: " + ", ".join(stale)
    )
