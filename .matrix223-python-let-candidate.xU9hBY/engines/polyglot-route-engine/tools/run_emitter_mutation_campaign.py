"""Mutation campaign against the emitter, and the score it yields.

The point of this tool is to produce a *number* for a question the route
evidence could not answer: are the tests strong enough to notice if the
emitter breaks? Every certification artefact in `routes/` reports
`p0_behavior_pass_rate: 1.0`, but a pass rate only says the existing cases
passed -- it says nothing about what a case set would catch. Four real defects
lived under a 1.0 pass rate because nine small-positive-integer cases cannot
reach them.

Each mutant below is a *plausible* regression: reverting one compensation the
emitter performs, of the kind a refactor or a merge could introduce. A mutant
is KILLED if the test suite fails on it and SURVIVED if the suite still passes.

    mutation score = killed / applicable

A surviving mutant is not a bug in the emitter -- it is a hole in the tests,
and names exactly which behaviour has no case covering it.

Usage:
    python3 tools/run_emitter_mutation_campaign.py [--tests tests/...] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMITTER = Path("src/elmos_polyglot_route/emitter.py")

#: Tests that need no toolchain beyond CPython and Node, so the campaign runs
#: anywhere the engine's own unit tests do.
DEFAULT_TESTS = (
    "tests/test_type_semantics.py",
    "tests/test_cpp_objc_swift.py",
    "tests/test_arithmetic_equivalence.py",
    "tests/test_property_differential.py",
    "tests/test_arithmetic_proof.py",
)


@dataclass(frozen=True)
class Mutant:
    identifier: str
    behaviour: str
    find: str
    replace: str


#: Each entry reverts one compensation. The `find` text is matched exactly and
#: must occur at least once, so a mutant that no longer applies is reported as
#: NOT_APPLICABLE rather than silently counted as killed.
MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        "rust-grouping",
        "Rust drops parentheses everywhere, reassociating nested expressions",
        '    if language == "rust" and top_level:\n        return rendered\n    return f"({rendered})"',
        '    if language == "rust":\n        return rendered\n    return f"({rendered})"',
    ),
    Mutant(
        "rust-grouping-outermost",
        "Rust parenthesises the outermost position too, which -D warnings rejects",
        '    if language == "rust" and top_level:\n        return rendered\n    return f"({rendered})"',
        '    return f"({rendered})"',
    ),
    Mutant(
        "java-overflow",
        "Java addition stops being checked and wraps again",
        '"+": ("Math.addExact", ()),',
        '"+": ("", ()),',
    ),
    Mutant(
        "python-overflow",
        "the Python range check is removed, so results grow past 2^63",
        "    if not _ELMOS_INTEGER_MIN <= value <= _ELMOS_INTEGER_MAX:",
        "    if False:",
    ),
    Mutant(
        "python-truncating-div",
        "Python integer division floors again instead of truncating",
        "        \"    quotient = abs(left) // abs(right)\\n\"",
        "        \"    quotient = left // right\\n\"",
    ),
    Mutant(
        "python-truncating-div-sign",
        "the sign correction on Python division is dropped",
        '        "    return _elmos_in_range(quotient if (left >= 0) == (right >= 0) else -quotient)\\n"',
        '        "    return _elmos_in_range(quotient)\\n"',
    ),
    Mutant(
        "python-zero-divisor",
        "Python stops raising on a zero divisor before the // does",
        '        "    if right == 0:\\n"',
        '        "    if False:\\n"',
    ),
    Mutant(
        "typescript-trunc",
        "TypeScript integer division stops truncating",
        'return f"_elmosRequireSafeInteger(Math.trunc({left} / _elmosRequireNonZero({right})))"',
        'return f"_elmosRequireSafeInteger({left} / _elmosRequireNonZero({right}))"',
    ),
    Mutant(
        "typescript-zero-divisor",
        "TypeScript division by zero answers Infinity again",
        'return f"_elmosRequireSafeInteger(Math.trunc({left} / _elmosRequireNonZero({right})))"',
        'return f"_elmosRequireSafeInteger(Math.trunc({left} / {right}))"',
    ),
    Mutant(
        "typescript-safe-integer",
        "the TypeScript safe-integer guard is removed from arithmetic",
        'return f"_elmosRequireSafeInteger({left} {operator} {right})"',
        'return f"({left} {operator} {right})"',
    ),
    Mutant(
        "typescript-strict-equality",
        "TypeScript reverts to == and its implicit coercion",
        'rendered = {"==": "===", "!=": "!=="}.get(operator, operator)',
        "rendered = operator",
    ),
    Mutant(
        "java-string-equality",
        "Java compares strings by reference again",
        'equality = f"{left}.equals({right})"',
        'equality = f"{left} == {right}"',
    ),
    Mutant(
        "rust-checked-mul",
        "Rust multiplication wraps instead of failing",
        '"*": ("checked_mul", _OVERFLOW_MESSAGE),',
        '"*": ("wrapping_mul", _OVERFLOW_MESSAGE),',
    ),
    Mutant(
        "go-overflow-predicate",
        "the Go addition overflow predicate loses its negative-operand arm",
        '        "    if (right > 0 && sum < left) || (right < 0 && sum > left) {\\n"',
        '        "    if right > 0 && sum < left {\\n"',
    ),
    Mutant(
        "go-min-over-minus-one",
        "Go stops rejecting INT64_MIN / -1 and wraps to INT64_MIN instead",
        '        "    if left == elmosIntegerMin && right == -1 {\\n"',
        '        "    if false {\\n"',
    ),
    Mutant(
        "go-subtraction-predicate",
        "the Go subtraction overflow predicate loses its positive-operand arm",
        '        "    if (right < 0 && difference < left) || (right > 0 && difference > left) {\\n"',
        '        "    if right < 0 && difference < left {\\n"',
    ),
    Mutant(
        "go-multiplication-round-trip",
        "the Go multiplication overflow check drops its division round-trip",
        '        "    if product/right != left {\\n"',
        '        "    if false {\\n"',
    ),
    Mutant(
        "python-parameter-guard",
        "Python stops rejecting arguments outside the canonical integer range",
        '                _require_helper(context, "integer_range")\n'
        '                lines.append(f"    _elmos_in_range({parameter.name})")',
        "                pass",
    ),
    Mutant(
        "cpp-least-literal",
        "the C/C++ most-negative literal goes back to a form that will not compile",
        '        return "INT64_MIN" if language == "cpp" else "LLONG_MIN"',
        '        return f"{value}LL"',
    ),
    Mutant(
        "float-zero-divisor",
        "the float divisor guard is removed, so Python raises where others answer Infinity",
        "        guard = _FLOAT_NON_ZERO_GUARD.get(language)",
        "        guard = None",
    ),
    Mutant(
        "typescript-parameter-guard",
        "TypeScript stops checking that incoming integers are representable",
        '                _require_helper(context, "safe_integer")\n'
        '                context.normalization_rules.add("typescript.parameter.integer.safe-integer")\n'
        '                context.normalization_rules.add("typescript.parameter.integer.negative-zero-normalized")\n'
        '                lines.append(f"    {parameter.name} = _elmosRequireSafeInteger({parameter.name});")',
        '                pass',
    ),
    Mutant(
        "integer-literal-range",
        "out-of-range integer literals are accepted instead of failing closed",
        "    if not types.INTEGER_MIN <= value <= types.INTEGER_MAX:",
        "    if False:",
    ),
    Mutant(
        "typescript-unsafe-literal",
        "TypeScript accepts literals it cannot represent exactly",
        '    if language == "typescript" and abs(value) > types.TYPESCRIPT_SAFE_INTEGER_MAX:',
        "    if False:",
    ),
)


@dataclass
class Outcome:
    identifier: str
    behaviour: str
    status: str  # KILLED / SURVIVED / NOT_APPLICABLE
    detail: str = ""


def _run_tests(workspace: Path, tests: tuple[str, ...]) -> tuple[bool, str]:
    completed = subprocess.run(  # noqa: S603 - fixed argv into a temp workspace
        [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", *tests],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=900,
        env={"PYTHONPATH": "src", "PATH": __import__("os").environ.get("PATH", "")},
    )
    return completed.returncode == 0, completed.stdout[-400:]


def run_campaign(tests: tuple[str, ...]) -> tuple[list[Outcome], float]:
    outcomes: list[Outcome] = []
    with tempfile.TemporaryDirectory() as base:
        pristine = Path(base) / "pristine"
        shutil.copytree(ROOT, pristine, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".*_cache"))
        present = [name for name in tests if (pristine / name).exists()]
        if not present:
            raise SystemExit(f"none of the requested test files exist: {tests}")
        baseline_ok, baseline_detail = _run_tests(pristine, tuple(present))
        if not baseline_ok:
            raise SystemExit(f"the unmutated suite must pass before mutating:\n{baseline_detail}")
        original = (pristine / EMITTER).read_text(encoding="utf-8")
        for mutant in MUTANTS:
            if mutant.find not in original:
                outcomes.append(
                    Outcome(mutant.identifier, mutant.behaviour, "NOT_APPLICABLE", "pattern absent")
                )
                continue
            workspace = Path(base) / mutant.identifier
            shutil.copytree(pristine, workspace)
            (workspace / EMITTER).write_text(
                original.replace(mutant.find, mutant.replace, 1), encoding="utf-8"
            )
            passed, detail = _run_tests(workspace, tuple(present))
            outcomes.append(
                Outcome(
                    mutant.identifier,
                    mutant.behaviour,
                    "SURVIVED" if passed else "KILLED",
                    "" if not passed else "no test noticed",
                )
            )
            shutil.rmtree(workspace, ignore_errors=True)
    applicable = [o for o in outcomes if o.status != "NOT_APPLICABLE"]
    killed = [o for o in applicable if o.status == "KILLED"]
    score = len(killed) / len(applicable) if applicable else 0.0
    return outcomes, score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", nargs="*", default=list(DEFAULT_TESTS))
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="exit non-zero below this score, for use as a gate",
    )
    arguments = parser.parse_args()
    outcomes, score = run_campaign(tuple(arguments.tests))
    width = max(len(o.identifier) for o in outcomes)
    for outcome in outcomes:
        print(f"  {outcome.status:<14} {outcome.identifier:<{width}}  {outcome.behaviour}")
    applicable = [o for o in outcomes if o.status != "NOT_APPLICABLE"]
    killed = sum(1 for o in applicable if o.status == "KILLED")
    print(f"\nmutation score {score:.1%}  ({killed}/{len(applicable)} killed)")
    survivors = [o for o in outcomes if o.status == "SURVIVED"]
    if survivors:
        print("\nsurvivors -- each names a behaviour with no case covering it:")
        for outcome in survivors:
            print(f"  - {outcome.identifier}: {outcome.behaviour}")
    if arguments.json:
        arguments.json.write_text(
            json.dumps(
                {
                    "mutation_score": score,
                    "killed": killed,
                    "applicable": len(applicable),
                    "outcomes": [asdict(o) for o in outcomes],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if score < arguments.min_score else 0


if __name__ == "__main__":
    sys.exit(main())
