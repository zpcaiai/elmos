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
import json
import subprocess
import sys
from pathlib import Path

import pytest
import z3  # type: ignore[import-untyped]

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
    pytest.fail(f"{target} {operator} was not proved: status={failure.status} detail={failure.counterexample}")


def test_solver_version_is_locked() -> None:
    assert z3.get_version_string() == "4.16.0"


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
    assert not stale, "these emitted helpers no longer match the proof models: " + ", ".join(stale)


def _result(status: str) -> object:
    obligation = proof.Obligation("go", "+", "THEOREM", "test obligation")
    return proof.Result(obligation, status, None)


@pytest.mark.parametrize("status", ["UNKNOWN", "TIMEOUT", "COUNTEREXAMPLE"])
def test_unresolved_campaign_statuses_fail_closed(status: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proof, "check_transcriptions", lambda: [])
    monkeypatch.setattr(proof, "discharge", lambda: [_result(status)])
    assert proof.main([]) == 1


def test_required_64_bit_campaign_rejects_bounded_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "check_transcriptions", lambda: [])
    monkeypatch.setattr(proof, "discharge", lambda: [_result("BOUNDED")])
    assert proof.main(["--require-64-bit"]) == 1


@pytest.mark.parametrize("operator", proof.OPERATORS)
def test_typescript_guard_abstraction_is_never_unconditional_proof(operator: str) -> None:
    status, detail = proof._typescript_verdict(operator)

    assert status == "PROVED_UNDER_ASSUMPTIONS"
    assert detail == ""


def test_required_64_bit_campaign_rejects_conditional_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "check_transcriptions", lambda: [])
    monkeypatch.setattr(
        proof,
        "discharge",
        lambda: [_result("PROVED_UNDER_ASSUMPTIONS")],
    )

    assert proof.main(["--require-64-bit"]) == 1


def test_conditional_proof_has_cli_marker_count_and_explicit_fail_on(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(proof, "check_transcriptions", lambda: [])
    monkeypatch.setattr(
        proof,
        "discharge",
        lambda: [_result("PROVED_UNDER_ASSUMPTIONS")],
    )

    assert proof.main(["--fail-on", "proved_under_assumptions"]) == 1
    output = capsys.readouterr().out
    assert "assumed" in output
    assert "0 proved unconditionally" in output
    assert "1 proved under assumptions" in output


def _single_payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    assert isinstance(payload, dict)
    return payload


def test_single_typescript_obligation_require_64_bit_fails_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = proof.main(["--obligation", "typescript", "+", "--require-64-bit"])

    assert exit_code == 1
    assert _single_payload(capsys)["status"] == "PROVED_UNDER_ASSUMPTIONS"


def test_single_obligation_respects_explicit_fail_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = proof.main(
        [
            "--obligation",
            "typescript",
            "+",
            "--fail-on",
            "proved_under_assumptions",
        ]
    )

    assert exit_code == 1
    assert _single_payload(capsys)["status"] == "PROVED_UNDER_ASSUMPTIONS"


def test_single_unconditional_proof_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = proof.main(["--obligation", "go", "+"])

    assert exit_code == 0
    assert _single_payload(capsys)["status"] == "PROVED"


@pytest.mark.parametrize(
    ("target", "operator", "diagnostic"),
    [
        ("ruby", "+", "unsupported obligation target"),
        ("go", "**", "unsupported obligation operator"),
    ],
)
def test_invalid_single_obligation_fails_closed(
    target: str,
    operator: str,
    diagnostic: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = proof.main(["--obligation", target, operator])

    assert exit_code == 1
    payload = _single_payload(capsys)
    assert payload["status"] == "UNKNOWN"
    assert diagnostic in str(payload["detail"])


def test_isolated_discharge_preserves_valid_worker_status_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "_solver_formulations", lambda *_args: ())
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout='{"status":"TIMEOUT","detail":"solver budget exhausted"}\n',
        stderr="fail-closed worker exit",
    )
    monkeypatch.setattr(proof.subprocess, "run", lambda *_args, **_kwargs: completed)

    status, detail, formulations = proof._discharge_isolated("go", "+")

    assert status == "TIMEOUT"
    assert detail == "solver budget exhausted"
    assert formulations == ()


def test_axiom_is_reported_but_never_counted_as_proved() -> None:
    payload = proof.campaign_payload([_result("AXIOM")])
    assert payload["all_required_proved"] is False
    assert payload["counts"]["PROVED"] == 0
    assert payload["counts"]["AXIOM"] == 1


def test_typescript_assumptions_are_persisted_and_not_counted_as_proved() -> None:
    obligation = proof.Obligation(
        "typescript",
        "+",
        "GUARD_ABSTRACTION",
        "test guard abstraction",
    )
    result = proof.Result(
        obligation,
        "PROVED_UNDER_ASSUMPTIONS",
        None,
        (),
        proof.TYPESCRIPT_GUARD_ABSTRACTION_ASSUMPTIONS,
    )

    payload = proof.campaign_payload([result])
    recorded = payload["obligations"][0]
    assert payload["all_required_proved"] is False
    assert payload["counts"]["PROVED"] == 0
    assert payload["counts"]["PROVED_UNDER_ASSUMPTIONS"] == 1
    assert recorded["unconditional_proof"] is False
    assert set(recorded["transcription_digests"]) == {"typescript safe-integer-guard"}
    assert "UNMODELED:IEEE-754-binary64-arithmetic-rounding-and-special-values" in recorded["assumptions"]
    assert "UNMODELED:Number.isSafeInteger-runtime-semantics" in recorded["assumptions"]
    assert "UNMODELED:real-emitted-expression-and-helper-transcription" in recorded["assumptions"]
