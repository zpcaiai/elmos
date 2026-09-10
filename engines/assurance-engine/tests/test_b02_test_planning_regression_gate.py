"""Tests for B02: Test planning, smoke gate, full regression, and gate engine."""

import time

from elmos_assurance_engine.bounded_repair import BoundedRepairLoop
from elmos_assurance_engine.contracts import GateDecision, sha256_digest
from elmos_assurance_engine.full_regression import RegressionRunner
from elmos_assurance_engine.gate_engine import GateEngine
from elmos_assurance_engine.planner import CoveragePlanner
from elmos_assurance_engine.scope import ScopeCompiler
from elmos_assurance_engine.smoke_gate import SmokeGateEvaluator


def test_b02_coverage_planner_denominator_freezing():
    scope = ScopeCompiler.compile_scope(
        tenant_id="t1", project_id="p1", run_id="r1",
        supported_features=["order-permission-flow", "payment-idempotency"],
    )
    obls = CoveragePlanner.compile_obligations(scope)
    assert obls.denominator == len(obls.obligations)
    assert obls.denominator > 0

    smoke = CoveragePlanner.select_smoke_obligations(obls)
    reg = CoveragePlanner.select_regression_obligations(obls)
    assert len(smoke) > 0
    assert len(reg) > 0
    assert len(smoke) + len(reg) == obls.denominator


def test_b02_smoke_gate_halts_on_failure():
    passing_results = [{"case_id": "smoke-1", "status": "PASSED"}, {"case_id": "smoke-2", "status": "PASSED"}]
    dec, reasons = SmokeGateEvaluator.evaluate(passing_results)
    assert dec == GateDecision.PASS

    failing_results = [{"case_id": "smoke-1", "status": "PASSED"}, {"case_id": "smoke-2", "status": "FAILED"}]
    dec_fail, reasons_fail = SmokeGateEvaluator.evaluate(failing_results)
    assert dec_fail == GateDecision.FAIL
    assert any("REGRESSION_EXECUTION_HALTED" in r for r in reasons_fail)


def test_b02_regression_runner_zero_test_rule():
    # ZERO-TEST RULE: Empty test execution must FAIL
    dec, reasons = RegressionRunner.evaluate([], expected_test_count=5)
    assert dec == GateDecision.FAIL
    assert any("ZERO_TESTS" in r for r in reasons)

    # Partial execution must FAIL
    partial = [{"case_id": "tc-1", "status": "PASSED"}]
    dec_partial, reasons_partial = RegressionRunner.evaluate(partial, expected_test_count=5)
    assert dec_partial == GateDecision.FAIL
    assert any("TEST_COUNT_UNDER_EXPECTED" in r for r in reasons_partial)

    # Full pass
    full = [{"case_id": f"tc-{i}", "status": "PASSED"} for i in range(5)]
    dec_full, reasons_full = RegressionRunner.evaluate(full, expected_test_count=5)
    assert dec_full == GateDecision.PASS


def test_b02_gate_engine_e5_requires_auditor_and_no_self_signing():
    now = int(time.time())
    request = {
        "tenant_id": "t1",
        "project_id": "p1",
        "run_id": "r1",
        "target_level": "E5",
        "revision_set": {"source": "a" * 64},
    }
    app_digest = sha256_digest(request)

    # When Ethen is NOT configured, E5 gate MUST return INCONCLUSIVE and forbid signing
    res = GateEngine.evaluate_gate(
        request=request,
        envelopes=(),
        blobs={},
        trusted_keys={},
        now=now,
        approved_request_digest=app_digest,
        ethen_configured=False,
    )
    assert res.verdict == GateDecision.INCONCLUSIVE
    assert res.production_signing_allowed is False
    assert any("AUDITOR_NOT_CONFIGURED" in r for r in res.reasons)


def test_b02_bounded_repair_loop_exhausts():
    loop = BoundedRepairLoop(max_attempts=2)
    cont1, msg1 = loop.record_attempt("c1", "p1", GateDecision.FAIL)
    assert cont1 is True

    cont2, msg2 = loop.record_attempt("c2", "p2", GateDecision.FAIL)
    assert cont2 is False
    assert "REPAIR_ATTEMPTS_EXHAUSTED" in msg2
