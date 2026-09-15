"""Industrial-grade automated test suite covering production certification gaps:

1. Hermetic container sandbox & environment fingerprinting
2. Chaos fault injection & resilient database channel with backoff and circuit breaker
3. Long-run soak testing & physical resource leak auditing (FDs, RSS, Threads)
4. Non-self-certification independent audit gate with anti-fabrication and cryptographic notarization
"""

from __future__ import annotations

import os
import time
import pytest

from elmos_proof_harness.hermetic_container import (
    EnvironmentFingerprint,
    HermeticContainerSandbox,
    IsolationLevel,
)
from elmos_proof_harness.resilience_channel import (
    ChaosConfig,
    ChaosFaultInjector,
    ChaosFaultType,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    NonRetryableError,
    ResilientDatabaseChannel,
)
from elmos_proof_harness.soak_auditor import (
    ResourceLeakAuditor,
    ResourceLeakError,
    SoakTestRunner,
)
from elmos_proof_harness.notary import CryptographicNotary
from elmos_proof_harness.independent_audit_gate import (
    CandidateEvidenceBundle,
    GateDecision,
    GateViolationReason,
    IndependentAuditGateRunner,
)


# ==============================================================================
# 1. HERMETIC CONTAINER & ENVIRONMENT FINGERPRINT TESTS
# ==============================================================================


def test_environment_fingerprint_detection() -> None:
    fp = EnvironmentFingerprint.detect()
    print(f"\n[HOST FINGERPRINT] OS: {fp.os_system} {fp.os_release}, Arch: {fp.arch}, Libc: {fp.libc_kind}")
    print(f"[CONTAINER ENGINES] Docker: {fp.docker_available}, Podman: {fp.podman_available}, Level: {fp.active_isolation_level.value}")

    assert fp.os_system in ("darwin", "linux", "windows")
    assert fp.arch != ""
    assert fp.python_version.startswith("3.")
    assert fp.active_isolation_level in (
        IsolationLevel.DOCKER_CONTAINER,
        IsolationLevel.PODMAN_CONTAINER,
        IsolationLevel.POSIX_RLIMIT_SANDBOX,
    )

    d = fp.to_dict()
    assert d["arch"] == fp.arch
    assert "libc_kind" in d


def test_hermetic_sandbox_execution_and_isolation() -> None:
    sandbox = HermeticContainerSandbox(force_posix_fallback=True)
    res = sandbox.run(
        ["python3", "-c", "import os; print('HERMETIC_ISOLATION_OK:' + str(os.getpid()))"],
        timeout_seconds=5.0,
        custom_env={"CUSTOM_TOKEN": "SAFE_VAL"},
    )
    print(f"\n[HERMETIC SANDBOX] Level: {res.isolation_level.value}, Exit: {res.exit_code}, Duration: {res.duration_ms}ms")
    print(f"[HERMETIC SANDBOX] Stdout: {res.stdout.strip()}")

    assert res.exit_code == 0
    assert "HERMETIC_ISOLATION_OK" in res.stdout
    assert res.duration_ms > 0
    assert res.timed_out is False
    assert res.isolation_level == IsolationLevel.POSIX_RLIMIT_SANDBOX


# ==============================================================================
# 2. CHAOS FAULT INJECTION & RESILIENT CHANNEL TESTS
# ==============================================================================


def test_chaos_fault_injection_and_backoff_recovery() -> None:
    """Verifies that ResilientDatabaseChannel automatically survives transient network drops."""
    chaos_config = ChaosConfig(
        enabled=True,
        failure_rate=1.0,
        fault_type=ChaosFaultType.CONNECTION_DROP,
        max_injections=2,  # Exactly 2 injected drops before physical network self-heals
    )
    fault_injector = ChaosFaultInjector(chaos_config)

    channel = ResilientDatabaseChannel(
        max_retries=4,
        base_backoff_seconds=0.02,
        max_backoff_seconds=0.1,
        fault_injector=fault_injector,
    )

    call_count = 0

    def database_transaction() -> str:
        nonlocal call_count
        call_count += 1
        return f"SUCCESSFUL_TRANSACTION_PAYLOAD_{call_count}"

    res = channel.execute(database_transaction)
    print(f"\n[RESILIENT CHANNEL] Success after retry: {res}, Total Calls: {channel.total_calls}, Retries: {channel.retried_calls}")

    assert res == "SUCCESSFUL_TRANSACTION_PAYLOAD_1"
    assert channel.retried_calls == 2
    metrics = channel.metrics()
    assert metrics.successful_calls == 1


def test_resilient_channel_non_retryable_fatal_error() -> None:
    channel = ResilientDatabaseChannel(max_retries=3)

    def fatal_operation() -> None:
        raise NonRetryableError("Fatal SQL syntax error or permission denied")

    with pytest.raises(NonRetryableError):
        channel.execute(fatal_operation)

    # Should not waste retries on fatal errors
    assert channel.retried_calls == 0


def test_circuit_breaker_tripping_and_cascade_prevention() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=0.2)
    channel = ResilientDatabaseChannel(max_retries=0, circuit_breaker=cb)

    def failing_op() -> None:
        raise ConnectionResetError("Target DB host unreachable")

    # Cause 3 failures to trip the circuit
    for _ in range(3):
        with pytest.raises(ConnectionResetError):
            channel.execute(failing_op)

    assert cb.state == CircuitState.OPEN
    print(f"\n[CIRCUIT BREAKER] State tripped to: {cb.state.value}")

    # Subsequent call must fail immediately without invoking the op
    with pytest.raises(CircuitBreakerOpenError):
        channel.execute(failing_op)

    assert channel.metrics().circuit_breaker_rejections == 1

    # Wait for recovery timeout to probe HALF_OPEN
    time.sleep(0.25)
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN
    print(f"[CIRCUIT BREAKER] Transitioned to: {cb.state.value} probe")


# ==============================================================================
# 3. SOAK TESTING & PHYSICAL RESOURCE LEAK AUDITING TESTS
# ==============================================================================


def test_soak_test_runner_zero_resource_leaks() -> None:
    """Executes intensive loop iterations and physically verifies 0 FD and 0 thread leaks."""
    runner = SoakTestRunner(max_allowed_rss_growth_mb=20.0, max_allowed_fd_leak=0)

    # Intensive workload allocating and freeing resources
    def workload(i: int) -> None:
        data = [x * 2 for x in range(1000)]
        d_map = {f"k_{k}": v for k, v in enumerate(data[:100])}
        assert len(d_map) == 100

    report = runner.run_soak(workload, iterations=200, warmup_iterations=10)
    print(
        f"\n[SOAK REPORT] Completed {report.iterations_completed} iterations | "
        f"FD Delta: {report.fd_delta} | Thread Delta: {report.thread_delta} | "
        f"RSS Growth: {report.rss_growth_mb:.2f}MB | P95 Latency: {report.p95_latency_ms:.3f}ms"
    )

    assert report.iterations_completed == 200
    assert report.has_fd_leak is False
    assert report.has_thread_leak is False
    assert report.fd_delta <= 0


def test_soak_test_runner_catches_intentional_fd_leak() -> None:
    """Proves the auditor actually detects real leaks rather than pretending to pass."""
    runner = SoakTestRunner(max_allowed_fd_leak=0)
    leaked_pipes: list[int] = []

    def leaky_workload(i: int) -> None:
        # Deliberately open pipe descriptors without closing
        r, w = os.pipe()
        leaked_pipes.extend([r, w])

    try:
        if ResourceLeakAuditor.get_open_fd_count() > 0:
            with pytest.raises(ResourceLeakError, match="open file descriptor leak"):
                runner.run_soak(leaky_workload, iterations=5, warmup_iterations=1)
            print("\n[SOAK LEAK DETECTOR] Successfully caught intentional physical FD leak!")
    finally:
        # Clean up leaked pipes
        for fd in leaked_pipes:
            try:
                os.close(fd)
            except Exception:
                pass


# ==============================================================================
# 4. INDEPENDENT AUDIT GATE & ANTI-FABRICATION TESTS (E0-E5 NON-SELF-CERT)
# ==============================================================================


def test_independent_audit_gate_zero_test_rule_rejection() -> None:
    runner = IndependentAuditGateRunner()
    bundle = CandidateEvidenceBundle(
        task_id="task-mock-01",
        executed_command="pytest tests/unit",
        exit_code=0,
        duration_ms=1200,
        test_count=0,  # Zero tests!
        pass_count=0,
        fail_count=0,
        stdout_digest="sha256-empty",
        stderr_digest="sha256-empty",
    )
    receipt = runner.evaluate_bundle(bundle)
    print(f"\n[INDEPENDENT GATE] Zero-Test verdict: {receipt.gate_decision.value}, Violations: {receipt.violations}")

    assert receipt.gate_decision == GateDecision.REJECTED
    assert any(GateViolationReason.ZERO_TEST_RULE.value in v for v in receipt.violations)


def test_independent_audit_gate_duration_zero_fabrication_rejection() -> None:
    runner = IndependentAuditGateRunner()
    bundle = CandidateEvidenceBundle(
        task_id="task-fake-02",
        executed_command="cargo test",
        exit_code=0,
        duration_ms=0,  # Physically impossible 0ms duration!
        test_count=50,
        pass_count=50,
        fail_count=0,
        stdout_digest="sha256-dummy",
        stderr_digest="sha256-dummy",
    )
    receipt = runner.evaluate_bundle(bundle)
    print(f"\n[INDEPENDENT GATE] 0ms Fabrication verdict: {receipt.gate_decision.value}, Violations: {receipt.violations}")

    assert receipt.gate_decision == GateDecision.REJECTED
    assert any(GateViolationReason.DURATION_ZERO_FABRICATION.value in v for v in receipt.violations)


def test_independent_audit_gate_unauthorized_self_certification_blocked() -> None:
    runner = IndependentAuditGateRunner()
    bundle = CandidateEvidenceBundle(
        task_id="task-illegal-claim-03",
        executed_command="mvn verify",
        exit_code=0,
        duration_ms=5000,
        test_count=10,
        pass_count=10,
        fail_count=0,
        stdout_digest="sha256-out",
        stderr_digest="sha256-err",
        self_attested_claim="CERTIFIED",  # Worker illegal attempt to self-certify!
    )
    receipt = runner.evaluate_bundle(bundle)
    print(f"\n[INDEPENDENT GATE] Self-Cert Violation verdict: {receipt.gate_decision.value}, Violations: {receipt.violations}")

    assert receipt.gate_decision == GateDecision.REJECTED
    assert any(GateViolationReason.UNAUTHORIZED_SELF_CERTIFICATION.value in v for v in receipt.violations)


def test_independent_audit_gate_valid_qualification_receipt() -> None:
    notary = CryptographicNotary(notary_id="audit-notary-prod")
    runner = IndependentAuditGateRunner(notary=notary)

    bundle = CandidateEvidenceBundle(
        task_id="task-genuine-prod-04",
        executed_command="pytest tests/test_real_industrial_integration.py",
        exit_code=0,
        duration_ms=2550,
        test_count=7,
        pass_count=7,
        fail_count=0,
        stdout_digest="a1b2c3d4e5f6...",
        stderr_digest="e3b0c44298fc...",
        self_attested_claim="DECLARED",
    )

    env = notary.notarize_evidence("task-genuine-prod-04", "PYTEST_RUN", {"status": "SUCCESS"})
    receipt = runner.evaluate_bundle(bundle, notarized_envelope=env)
    print(f"\n[INDEPENDENT GATE] Authoritative decision: {receipt.gate_decision.value}")
    print(f"[INDEPENDENT GATE] Passed Invariants: {receipt.passed_invariants}")
    print(f"[INDEPENDENT GATE] Sealed Receipt Envelope: {receipt.notary_envelope.envelope_id if receipt.notary_envelope else None}")

    assert receipt.gate_decision == GateDecision.LOCAL_ENGINEERING_PASSED
    assert len(receipt.violations) == 0
    assert "NON_SELF_CERTIFICATION_HONORED" in receipt.passed_invariants
    assert "CRYPTOGRAPHIC_SIGNATURE_VERIFIED" in receipt.passed_invariants
    assert receipt.notary_envelope is not None
    assert receipt.notary_envelope.notary_id == "audit-notary-prod"
