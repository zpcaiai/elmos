"""Tests for Formal Verification Engine and Counterexample-to-Test Loop."""

from __future__ import annotations

from unittest.mock import MagicMock


from elmos_proof_harness.adapter_drivers import AdapterDriverRegistry, DriverExecutionResult
from elmos_proof_harness.adapters import AdapterStatus
from elmos_proof_harness.formal_verifier import (
    FormalVerificationEngine,
    ObligationKind,
    ProofObligation,
    VerificationVerdict,
)


def test_formal_verifier_proved() -> None:
    # Mock driver returning unsat
    mock_registry = MagicMock(spec=AdapterDriverRegistry)
    mock_registry.execute_driver.return_value = DriverExecutionResult(
        status=AdapterStatus.SUCCEEDED,
        exit_code=0,
        stdout="unsat\n",
        stderr="",
        elapsed_ms=45,
        parsed_output={"verdict": "UNSAT"},
        tool_version="z3-4.12.2",
        tool_digest="sha256-z3-bin",
    )

    engine = FormalVerificationEngine(mock_registry)
    obligation = ProofObligation(
        obligation_id="obl-bounds-01",
        kind=ObligationKind.BOUNDS_CHECK,
        symbol="ArraySlice::get",
        preconditions=("0 <= index", "index < length"),
        postconditions=("result != null",),
        negated_goal_smt2="(declare-const i Int) (assert (< i 0))",
    )

    cert = engine.verify_obligation(obligation, solver_name="z3")
    assert cert.verdict == VerificationVerdict.PROVED
    assert cert.solver == "z3"
    assert cert.tool_version == "z3-4.12.2"
    assert cert.proof_hash is not None
    assert cert.counterexample is None
    assert cert.generated_test_code is None


def test_formal_verifier_refuted_with_counterexample_and_test() -> None:
    # Mock driver returning sat with model
    mock_model = (
        "sat\n"
        "(model\n"
        "  (define-fun x () Int\n"
        "    -5)\n"
        "  (define-fun flag () Bool\n"
        "    true)\n"
        ")\n"
    )
    mock_registry = MagicMock(spec=AdapterDriverRegistry)
    mock_registry.execute_driver.return_value = DriverExecutionResult(
        status=AdapterStatus.SUCCEEDED,
        exit_code=0,
        stdout=mock_model,
        stderr="",
        elapsed_ms=80,
        parsed_output={"verdict": "SAT"},
        tool_version="z3-4.12.2",
        tool_digest="sha256-z3-bin",
    )

    engine = FormalVerificationEngine(mock_registry)
    obligation = ProofObligation(
        obligation_id="obl-positivity-02",
        kind=ObligationKind.ARITHMETIC_OVERFLOW,
        symbol="Math::sqrt",
        preconditions=(),
        postconditions=("x >= 0",),
        negated_goal_smt2="(declare-const x Int) (assert (< x 0))",
    )

    cert = engine.verify_obligation(obligation, solver_name="z3")
    assert cert.verdict == VerificationVerdict.REFUTED
    assert cert.counterexample is not None
    assert cert.counterexample.assignments["x"] == -5
    assert cert.counterexample.assignments["flag"] is True

    # Check generated regression test
    assert cert.generated_test_code is not None
    assert "def test_formal_counterexample_obl_positivity_02()" in cert.generated_test_code
    assert "inputs = {'x': -5, 'flag': True}" in cert.generated_test_code

    # Verify serialization
    data = cert.to_dict()
    assert data["verdict"] == "REFUTED"
    assert data["has_generated_test"] is True
    assert data["counterexample"]["x"] == -5


def test_formal_verifier_timeout() -> None:
    mock_registry = MagicMock(spec=AdapterDriverRegistry)
    mock_registry.execute_driver.return_value = DriverExecutionResult(
        status=AdapterStatus.TIMED_OUT,
        exit_code=-1,
        stdout="",
        stderr="Timeout",
        elapsed_ms=10000,
        parsed_output={},
        tool_version="z3-4.12.2",
        tool_digest="sha256-z3-bin",
    )
    engine = FormalVerificationEngine(mock_registry)
    obligation = ProofObligation(
        obligation_id="obl-timeout-01",
        kind=ObligationKind.GENERIC_CONTRACT,
        symbol="ComplexLoop::run",
        preconditions=(),
        postconditions=(),
        negated_goal_smt2="",
    )
    cert = engine.verify_obligation(obligation)
    assert cert.verdict == VerificationVerdict.TIMEOUT
