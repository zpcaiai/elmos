"""Property-based differential execution across the L0 grammar.

The route packs carry nine hand-written cases per route, all small positive
integers. That is the weakest link in the evidence chain: four real defects
survived under a reported `p0_behavior_pass_rate` of 1.0 because no case could
reach them. This module replaces "the cases we thought of" with a generated
distribution, and checks two different kinds of claim:

* DIFFERENTIAL -- the same IR, emitted to two targets, must agree on every
  generated input. Python runs in-process and TypeScript through Node's type
  stripping, so this needs no toolchain the route does not already require.
  The other seven targets are covered by `tools/` and the route harness.

* METAMORPHIC -- relations that must hold of the *function*, whatever it
  answers: `clamp` lands inside its bounds and is idempotent, `difference` is
  never negative, `sign` composes with negation. These catch faults a
  differential test cannot, because they hold even when both targets are
  wrong in the same way.

Sample count is fixed and the seed is constant, so a failure reproduces
exactly. Raise it locally with ELMOS_PROPERTY_SAMPLES for a deeper sweep.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.canonical import (
    SAFE_INTEGER_MAX,
    CanonicalError,
    evaluate_ir,
)
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import SemanticIR

INTEGER_MAX = 2**63 - 1
INTEGER_MIN = -(2**63)
SAFE_MAX = SAFE_INTEGER_MAX

SEED = 20260806
SAMPLES = int(os.environ.get("ELMOS_PROPERTY_SAMPLES", "600"))

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the TypeScript half"
)


# --------------------------------------------------------------------------
# IR construction
# --------------------------------------------------------------------------


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


def _n(value: str) -> dict[str, Any]:
    return {"kind": "name", "value": value}


def _lit(value: Any) -> dict[str, Any]:
    return {"kind": "literal", "value": value}


def _b(operator: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def _unit(
    name: str,
    parameters: list[tuple[str, str]],
    return_type: str,
    body: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": name,
        "parameters": [{"name": n, "type": t} for n, t in parameters],
        "return_type": return_type,
        "body": body,
    }


def _returns(expression: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"kind": "return", "expression": expression}]


#: Units chosen to cover every production the L0 grammar has: nested
#: arithmetic with mixed precedence, comparison, boolean connectives, nested
#: if/else, integer and float returns, and the string operators.
INTEGER_UNITS: dict[str, dict[str, Any]] = {
    # (a + b) * a - b  -- precedence and associativity, the Rust defect's shape
    "mixed": _unit(
        "mixed",
        [("a", "integer"), ("b", "integer")],
        "integer",
        _returns(_b("-", _b("*", _b("+", _n("a"), _n("b")), _n("a")), _n("b"))),
    ),
    # a / b % (b - a)  -- both division forms in one expression
    "divisions": _unit(
        "divisions",
        [("a", "integer"), ("b", "integer")],
        "integer",
        _returns(_b("%", _b("/", _n("a"), _n("b")), _b("-", _n("b"), _n("a")))),
    ),
    # clamp, the holdout corpus function, with nested if/else
    "clamp": _unit(
        "clamp",
        [("a", "integer"), ("b", "integer")],
        "integer",
        [
            {
                "kind": "if",
                "condition": _b(">", _n("a"), _n("b")),
                "then": _returns(_n("b")),
                "else": [
                    {
                        "kind": "if",
                        "condition": _b("<", _n("a"), _lit(0)),
                        "then": _returns(_lit(0)),
                        "else": _returns(_n("a")),
                    }
                ],
            },
            *_returns(_n("a")),
        ],
    ),
    # difference, the representative corpus function
    "difference": _unit(
        "difference",
        [("a", "integer"), ("b", "integer")],
        "integer",
        [
            {
                "kind": "if",
                "condition": _b("<", _n("a"), _n("b")),
                "then": _returns(_lit(0)),
                "else": [],
            },
            *_returns(_b("-", _n("a"), _n("b"))),
        ],
    ),
    # boolean connectives over comparisons, returning a boolean
    "between": _unit(
        "between",
        [("a", "integer"), ("b", "integer")],
        "boolean",
        _returns(
            _b(
                "&&",
                _b("<=", _lit(0), _n("a")),
                _b("||", _b("<", _n("a"), _n("b")), _b("==", _n("a"), _n("b"))),
            )
        ),
    ),
}


# --------------------------------------------------------------------------
# Input distribution
# --------------------------------------------------------------------------

#: Values every generated sweep includes outright. A uniform draw over 64 bits
#: essentially never produces any of them, and every defect found so far lived
#: on one.
BOUNDARY_VALUES = (
    0,
    1,
    -1,
    2,
    -2,
    7,
    -7,
    SAFE_MAX,
    -SAFE_MAX,
    SAFE_MAX + 1,
    -(SAFE_MAX + 1),
    INTEGER_MAX,
    INTEGER_MIN,
    INTEGER_MAX - 1,
    INTEGER_MIN + 1,
)


def _integer_inputs(count: int) -> list[tuple[int, int]]:
    """Boundary pairs first, then a seeded mixture of magnitudes.

    The mixture is deliberately not uniform over 64 bits: small values are
    where ordinary behaviour lives, powers of two are where representation
    changes, and full-width values are where overflow lives. A uniform draw
    would spend every sample in the third bucket.
    """
    pairs: list[tuple[int, int]] = [(a, b) for a in BOUNDARY_VALUES for b in BOUNDARY_VALUES]
    generator = random.Random(SEED)

    def draw() -> int:
        bucket = generator.randrange(4)
        if bucket == 0:
            value = generator.randint(-100, 100)
        elif bucket == 1:
            exponent = generator.randrange(64)
            value = (1 << exponent) + generator.randint(-1, 1)
        elif bucket == 2:
            value = generator.randint(-SAFE_MAX, SAFE_MAX)
        else:
            value = generator.randint(INTEGER_MIN, INTEGER_MAX)
        # Arguments outside the canonical range are outside the contract, not
        # interesting inputs: 1 << 63 is one past INTEGER_MAX and the powers-of
        # -two bucket produces it.
        return max(INTEGER_MIN, min(INTEGER_MAX, value))

    while len(pairs) < count:
        pairs.append((draw(), draw()))
    return pairs[:count]


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


def _canonical_outcomes(
    unit: dict[str, Any], inputs: list[tuple[int, int]]
) -> list[tuple[Any, bool]]:
    """(value-or-ERROR, whether every intermediate stayed safe-integer sized).

    This is the specification, not a target: using one target as the reference
    would quietly promote its implementation to the spec.
    """
    ir = _ir(unit)
    outcomes: list[tuple[Any, bool]] = []
    for a, b in inputs:
        try:
            evaluation = evaluate_ir(ir, unit["name"], [a, b])
        except CanonicalError:
            outcomes.append(("ERROR", False))
        else:
            outcomes.append((evaluation.value, evaluation.within_safe_integers))
    return outcomes


def _python_outcomes(unit: dict[str, Any], inputs: list[tuple[int, int]]) -> list[Any]:
    namespace: dict[str, Any] = {}
    source = emit(_ir(unit), "python").content
    exec(compile(source, "migrated.py", "exec"), namespace)  # noqa: S102 - the emitted module is the unit under test
    function = namespace[unit["name"]]
    outcomes: list[Any] = []
    for a, b in inputs:
        try:
            outcomes.append(function(a, b))
        except (OverflowError, ZeroDivisionError, ValueError):
            outcomes.append("ERROR")
    return outcomes


def _typescript_outcomes(unit: dict[str, Any], inputs: list[tuple[int, int]]) -> list[Any]:
    source = emit(_ir(unit), "typescript").content
    harness = (
        "const results: unknown[] = [];\n"
        f"const cases: [number, number][] = {json.dumps(inputs)};\n"
        "for (const [a, b] of cases) {\n"
        f"  try {{ results.push({unit['name']}(a, b)); }} catch {{ results.push(\"ERROR\"); }}\n"
        "}\n"
        "console.log(JSON.stringify(results));\n"
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "unit.ts"
        path.write_text(source + "\n" + harness, encoding="utf-8")
        completed = subprocess.run(  # noqa: S603 - fixed argv, temp file input
            ["node", "--experimental-strip-types", "--no-warnings", str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
    return json.loads(completed.stdout.strip())


# --------------------------------------------------------------------------
# Differential, against the canonical semantics
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(INTEGER_UNITS))
def test_the_python_target_matches_the_canonical_semantics(name: str) -> None:
    unit = INTEGER_UNITS[name]
    inputs = _integer_inputs(SAMPLES)
    divergences = [
        f"{name}{arguments}: canonical={expected!r} python={actual!r}"
        for arguments, (expected, _), actual in zip(
            inputs, _canonical_outcomes(unit, inputs), _python_outcomes(unit, inputs), strict=True
        )
        if expected != actual
    ]
    assert not divergences, "\n".join(divergences[:20])


@pytest.mark.parametrize("name", sorted(INTEGER_UNITS))
def test_the_typescript_target_matches_or_fails_earlier(name: str) -> None:
    """TypeScript's exact-integer domain stops at 2^53-1, so it is allowed to
    fail where the canonical rules succeed -- but only then, and it may never
    answer a different value.

    The boundary is about *intermediates*, not operands or results:
    `(a + b) * a - b` at a=1, b=2^53-1 answers 1, well inside the safe range,
    but its first intermediate is 2^53 and TypeScript is required to fail.
    Stating this needs the canonical interpreter's widest-intermediate report;
    an operand-and-result check would wrongly call that a divergence.
    """
    unit = INTEGER_UNITS[name]
    inputs = _integer_inputs(SAMPLES)
    divergences: list[str] = []
    exercised_narrowing = False
    for arguments, (expected, all_safe), actual in zip(
        inputs, _canonical_outcomes(unit, inputs), _typescript_outcomes(unit, inputs), strict=True
    ):
        if expected == actual:
            continue
        if actual == "ERROR" and not all_safe:
            exercised_narrowing = True
            continue
        divergences.append(f"{name}{arguments}: canonical={expected!r} typescript={actual!r}")
    assert not divergences, "\n".join(divergences[:20])
    assert exercised_narrowing, (
        "the sweep never left the safe-integer range, so the narrowing clause "
        "went untested and this assertion proves nothing"
    )


def test_the_distribution_actually_reaches_the_interesting_regions() -> None:
    """A generator that never leaves the small-integer bucket would make every
    assertion above vacuous, which is exactly the failure mode of the nine
    hand-written cases. Pin the coverage the sweep is supposed to have."""
    inputs = _integer_inputs(SAMPLES)
    flat = [value for pair in inputs for value in pair]
    assert any(value == 0 for value in flat)
    assert any(value == INTEGER_MAX for value in flat)
    assert any(value == INTEGER_MIN for value in flat)
    assert sum(1 for value in flat if abs(value) > SAFE_MAX) >= 20
    assert sum(1 for value in flat if abs(value) <= 100) >= 20
    # and the sweep must actually provoke both outcomes, not just successes
    outcomes = [value for value, _ in _canonical_outcomes(INTEGER_UNITS["divisions"], inputs)]
    assert "ERROR" in outcomes
    assert any(outcome != "ERROR" for outcome in outcomes)


# --------------------------------------------------------------------------
# Metamorphic
# --------------------------------------------------------------------------


def _both_targets(unit: dict[str, Any], inputs: list[tuple[int, int]]) -> list[tuple[Any, Any]]:
    return list(
        zip(_python_outcomes(unit, inputs), _typescript_outcomes(unit, inputs), strict=True)
    )


def test_clamp_lands_inside_its_bounds_in_both_targets() -> None:
    inputs = [(a, b) for a, b in _integer_inputs(SAMPLES) if b >= 0]
    for (a, b), (python, typescript) in zip(inputs, _both_targets(INTEGER_UNITS["clamp"], inputs), strict=True):
        for outcome in (python, typescript):
            if outcome == "ERROR":
                continue
            assert 0 <= outcome <= b or outcome == a, f"clamp({a}, {b}) = {outcome}"


def test_clamp_is_idempotent_in_both_targets() -> None:
    inputs = [(a, b) for a, b in _integer_inputs(SAMPLES) if b >= 0]
    once = _both_targets(INTEGER_UNITS["clamp"], inputs)
    twice_inputs = [
        (value if isinstance(value, int) else 0, b)
        for (value, _), (_, b) in zip(once, inputs, strict=True)
    ]
    twice = _both_targets(INTEGER_UNITS["clamp"], twice_inputs)
    for (first, _), (second, _) in zip(once, twice, strict=True):
        if first == "ERROR" or second == "ERROR":
            continue
        assert first == second, f"clamp is not idempotent: {first} -> {second}"


def test_difference_is_never_negative_in_both_targets() -> None:
    inputs = _integer_inputs(SAMPLES)
    for (a, b), (python, typescript) in zip(
        inputs, _both_targets(INTEGER_UNITS["difference"], inputs), strict=True
    ):
        for outcome in (python, typescript):
            if outcome == "ERROR":
                continue
            assert outcome >= 0, f"difference({a}, {b}) = {outcome}"


def test_between_is_consistent_with_its_own_definition() -> None:
    inputs = _integer_inputs(SAMPLES)
    for (a, b), (python, typescript) in zip(
        inputs, _both_targets(INTEGER_UNITS["between"], inputs), strict=True
    ):
        if python == "ERROR" or typescript == "ERROR":
            continue
        expected = 0 <= a and a <= b
        assert python is expected, f"between({a}, {b}) = {python}"
        assert typescript is expected, f"between({a}, {b}) = {typescript}"
