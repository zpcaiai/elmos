import pytest
from elmos_spring_modernization import (
    SpringModernizationFixpointGuard,
    GuardVerdict,
    HumanEscalationDossier,
)


def test_converging_steps_are_allowed():
    guard = SpringModernizationFixpointGuard(max_iterations_per_file=5)
    file_p = "src/main/java/com/example/UserService.java"

    # Step 1: Replace javax.servlet with jakarta.servlet
    v1 = guard.record_step(
        file_path=file_p,
        rule_name="JAKARTA_NAMESPACE_RULE",
        before_content="import javax.servlet.http.HttpServletRequest;",
        after_content="import jakarta.servlet.http.HttpServletRequest;",
    )
    assert v1.allowed is True
    assert v1.circuit_open is False
    assert v1.reason == "STEP_ACCEPTED_CONVERGING"

    # Step 2: Replace @Autowired with constructor injection
    v2 = guard.record_step(
        file_path=file_p,
        rule_name="CONSTRUCTOR_INJECTION_RULE",
        before_content="import jakarta.servlet.http.HttpServletRequest;\n@Autowired private UserRepository repo;",
        after_content="import jakarta.servlet.http.HttpServletRequest;\nprivate final UserRepository repo;",
    )
    assert v2.allowed is True
    assert v2.circuit_open is False
    assert guard.is_healthy() is True


def test_oscillation_doom_loop_trips_circuit_breaker():
    guard = SpringModernizationFixpointGuard(max_iterations_per_file=5)
    file_p = "src/main/java/com/example/OrderService.java"

    code_state_a = "public String getStatus() { return Status.ACTIVE.name(); }"
    code_state_b = "public String getStatus() { return Status.ACTIVE.toString(); }"

    # Step 1: Rule 1 converts A -> B
    v1 = guard.record_step(
        file_path=file_p,
        rule_name="ENUM_TO_STRING_RULE",
        before_content=code_state_a,
        after_content=code_state_b,
    )
    assert v1.allowed is True

    # Step 2: Rule 2 reverts B -> A (Oscillation detected!)
    v2 = guard.record_step(
        file_path=file_p,
        rule_name="ENUM_TO_NAME_RULE",
        before_content=code_state_b,
        after_content=code_state_a,
    )
    assert v2.allowed is False
    assert v2.circuit_open is True
    assert v2.reason == "OSCILLATION_DOOM_LOOP_DETECTED"
    assert v2.escalation is not None
    assert v2.escalation.oscillation_detected is True
    assert "ENUM_TO_NAME_RULE" in v2.escalation.conflicting_rules
    assert guard.is_healthy() is False

    # Step 3: Any further attempt on this file is blocked
    v3 = guard.record_step(
        file_path=file_p,
        rule_name="ANOTHER_RULE",
        before_content=code_state_a,
        after_content="public String getStatus() { return null; }",
    )
    assert v3.allowed is False
    assert v3.circuit_open is True


def test_max_iteration_budget_trips_circuit_breaker():
    guard = SpringModernizationFixpointGuard(max_iterations_per_file=3)
    file_p = "src/main/java/com/example/PaymentService.java"

    # Apply 3 distinct steps
    guard.record_step(file_p, "RULE_1", "state_0", "state_1")
    guard.record_step(file_p, "RULE_2", "state_1", "state_2")
    guard.record_step(file_p, "RULE_3", "state_2", "state_3")

    # Step 4 exceeds max_iterations_per_file=3
    v4 = guard.record_step(file_p, "RULE_4", "state_3", "state_4")
    assert v4.allowed is False
    assert v4.circuit_open is True
    assert v4.reason == "MAX_ITERATIONS_EXCEEDED"
    assert v4.escalation is not None
    assert "Manual human review required" in v4.escalation.recommendation
