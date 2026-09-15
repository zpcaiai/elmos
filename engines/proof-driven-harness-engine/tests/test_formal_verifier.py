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


def test_sexpr_parser_and_tokenizer() -> None:
    from elmos_proof_harness.formal_verifier import SExprParser

    smt_text = """
    ; SMT-LIB2 model comment
    (model
      (define-fun |escaped_name| () (_ BitVec 32) #x0000002a)
      (define-fun message () String "hello \\"world\\"")
      (define-fun arr () (Array Int Int) (store ((as const (Array Int Int)) 0) 5 42))
    )
    """
    tokens = SExprParser.tokenize(smt_text)
    assert "(" in tokens
    assert "define-fun" in tokens
    assert "#x0000002a" in tokens

    parsed = SExprParser.parse(smt_text)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    model_form = parsed[0]
    assert model_form[0] == "model"


def test_smt_value_evaluator_bitvector_array_and_numbers() -> None:
    from elmos_proof_harness.formal_verifier import SMTValueEvaluator

    # BitVector tests
    assert SMTValueEvaluator.evaluate("#x0000002a") == 42
    assert SMTValueEvaluator.evaluate("#b00101010") == 42
    assert SMTValueEvaluator.evaluate(["_", "bv128", "32"]) == 128
    assert SMTValueEvaluator.format_sort(["_", "BitVec", "32"]) == "BitVec(32)"

    # Array tests
    arr_expr = ["store", [["as", "const", ["Array", "Int", "Int"]], "0"], "10", "99"]
    arr_val = SMTValueEvaluator.evaluate(arr_expr)
    assert isinstance(arr_val, dict)
    assert arr_val["__default__"] == 0
    assert arr_val[10] == 99
    assert SMTValueEvaluator.format_sort(["Array", "Int", "Int"]) == "Array(Int, Int)"

    # Negative and division tests
    assert SMTValueEvaluator.evaluate(["-", "15"]) == -15
    assert SMTValueEvaluator.evaluate(["/", "10", "2"]) == 5.0
    assert SMTValueEvaluator.evaluate('"quoted string"') == "quoted string"


def test_formal_verifier_refuted_complex_counterexample_executable() -> None:
    from elmos_proof_harness.formal_verifier import SMTValueEvaluator

    mock_complex_model = """
    sat
    (model
      (define-fun offset () Int (- 42))
      (define-fun mask () (_ BitVec 32) #x000000ff)
      (define-fun status_code () String "OUT_OF_BOUNDS")
      (define-fun cache_table () (Array Int Int)
        (store (store ((as const (Array Int Int)) 0) 1 100) 2 200))
    )
    """
    mock_registry = MagicMock(spec=AdapterDriverRegistry)
    mock_registry.execute_driver.return_value = DriverExecutionResult(
        status=AdapterStatus.SUCCEEDED,
        exit_code=0,
        stdout=mock_complex_model,
        stderr="",
        elapsed_ms=120,
        parsed_output={"verdict": "SAT"},
        tool_version="z3-4.12.2",
        tool_digest="sha256-z3-bin",
    )

    engine = FormalVerificationEngine(mock_registry)
    obligation = ProofObligation(
        obligation_id="obl-complex-mem-01",
        kind=ObligationKind.BOUNDS_CHECK,
        symbol="MemoryBuffer::read_word",
        preconditions=(),
        postconditions=("offset >= 0",),
        negated_goal_smt2="(check-sat)",
    )

    cert = engine.verify_obligation(obligation, solver_name="z3")
    assert cert.verdict == VerificationVerdict.REFUTED
    assert cert.counterexample is not None

    # Check extracted values
    assignments = cert.counterexample.assignments
    assert assignments["offset"] == -42
    assert assignments["mask"] == 255
    assert assignments["status_code"] == "OUT_OF_BOUNDS"
    assert assignments["cache_table"] == {"__default__": 0, 1: 100, 2: 200}

    # Check sorts metadata
    sorts = cert.counterexample.sorts
    assert sorts["offset"] == "Int"
    assert sorts["mask"] == "BitVec(32)"
    assert sorts["cache_table"] == "Array(Int, Int)"

    # Verify that the generated regression test code is runnable Python
    assert cert.generated_test_code is not None
    test_scope: dict[str, Any] = {}
    exec(cert.generated_test_code, test_scope)

    # Execute the generated test function!
    test_fn_name = "test_formal_counterexample_obl_complex_mem_01"
    assert test_fn_name in test_scope
    test_scope[test_fn_name]()  # Must run without assertion errors!

