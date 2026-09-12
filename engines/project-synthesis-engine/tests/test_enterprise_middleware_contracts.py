"""Tests for Enterprise Middleware Contracts & Distributed Saga Coordination."""

from __future__ import annotations

import pytest

from elmos_project_synthesis.enterprise_production_contract import (
    EnterpriseMiddlewareConfig,
    SagaDefinition,
    SagaStep,
)
from elmos_project_synthesis.saga_coordinator import (
    SagaCoordinator,
    SagaCoordinatorError,
)


def test_enterprise_middleware_configuration():
    cfg = EnterpriseMiddlewareConfig()
    assert cfg.redis_pool_size == 50
    assert cfg.redis_socket_timeout_seconds == 2.0
    assert cfg.null_sentinel == "__ELMOS_NULL_SENTINEL__"
    assert cfg.broker_type == "kafka"
    assert cfg.kafka_default_brokers == "localhost:9092"
    assert cfg.enable_w3c_trace_context is True
    assert cfg.outbox_batch_size == 50


def test_saga_coordinator_successful_workflow():
    coordinator = SagaCoordinator()

    saga = SagaDefinition(
        saga_id="order-create-saga",
        name="OrderCreationWorkflow",
        steps=(
            SagaStep(
                step_id="step-1",
                name="validate_order",
                action_endpoint="/api/v1/orders/validate",
                compensation_endpoint="/api/v1/orders/cancel",
            ),
            SagaStep(
                step_id="step-2",
                name="reserve_credit",
                action_endpoint="/api/v1/credits/reserve",
                compensation_endpoint="/api/v1/credits/release",
            ),
            SagaStep(
                step_id="step-3",
                name="allocate_stock",
                action_endpoint="/api/v1/inventory/allocate",
                compensation_endpoint="/api/v1/inventory/deallocate",
            ),
        ),
    )
    coordinator.register_saga(saga)

    # Handlers
    step_calls = []
    comp_calls = []

    def handle_validate(payload):
        step_calls.append("validate")
        return {"validated": True}

    def handle_credit(payload):
        step_calls.append("credit")
        return {"credit_reserved": 100.0}

    def handle_stock(payload):
        step_calls.append("stock")
        return {"stock_allocated": 2}

    step_handlers = {
        "validate_order": handle_validate,
        "reserve_credit": handle_credit,
        "allocate_stock": handle_stock,
    }
    comp_handlers = {
        "validate_order": lambda p: comp_calls.append("comp_validate"),
        "reserve_credit": lambda p: comp_calls.append("comp_credit"),
        "allocate_stock": lambda p: comp_calls.append("comp_stock"),
    }

    # Start and run
    record = coordinator.start_saga("order-create-saga", "exec-001", "tenant-alpha", {"order_id": "ord-101"})
    assert record.status == "PENDING"

    final_record = coordinator.run_workflow("exec-001", step_handlers, comp_handlers)
    assert final_record.status == "COMPLETED"
    assert final_record.current_step == 3
    assert final_record.payload["validated"] is True
    assert final_record.payload["credit_reserved"] == 100.0
    assert final_record.payload["stock_allocated"] == 2
    assert step_calls == ["validate", "credit", "stock"]
    assert comp_calls == []  # No compensation on success

    # Verify Journal
    journal = coordinator.get_journal("exec-001")
    event_types = [entry["event_type"] for entry in journal]
    assert event_types == [
        "SAGA_STARTED",
        "SAGA_RUNNING",
        "STEP_COMPLETED",
        "STEP_COMPLETED",
        "STEP_COMPLETED",
        "SAGA_COMPLETED",
    ]


def test_saga_coordinator_failure_and_lifo_compensation():
    coordinator = SagaCoordinator()

    saga = SagaDefinition(
        saga_id="payment-saga",
        name="PaymentWorkflow",
        steps=(
            SagaStep(
                step_id="step-1",
                name="step_one",
                action_endpoint="/step1",
                compensation_endpoint="/step1/revert",
            ),
            SagaStep(
                step_id="step-2",
                name="step_two",
                action_endpoint="/step2",
                compensation_endpoint="/step2/revert",
            ),
            SagaStep(
                step_id="step-3",
                name="step_three",
                action_endpoint="/step3",
                compensation_endpoint="/step3/revert",
            ),
        ),
    )
    coordinator.register_saga(saga)

    compensated = []

    step_handlers = {
        "step_one": lambda p: {"step1": "done"},
        "step_two": lambda p: {"step2": "done"},
        "step_three": lambda p: (_ for _ in ()).throw(RuntimeError("External Bank Outage")),
    }
    comp_handlers = {
        "step_one": lambda p: compensated.append("step_one"),
        "step_two": lambda p: compensated.append("step_two"),
        "step_three": lambda p: compensated.append("step_three"),
    }

    coordinator.start_saga("payment-saga", "exec-fail-001", "tenant-alpha", {"tx": "tx-999"})
    final_record = coordinator.run_workflow("exec-fail-001", step_handlers, comp_handlers)

    assert final_record.status == "COMPENSATED"
    assert "External Bank Outage" in (final_record.error or "")

    # Check LIFO order: step_two was compensated first, then step_one!
    # step_three was not completed so it is not compensated.
    assert compensated == ["step_two", "step_one"]

    # Verify Journal
    journal = coordinator.get_journal("exec-fail-001")
    event_types = [entry["event_type"] for entry in journal]
    assert "SAGA_COMPENSATING" in event_types
    assert "SAGA_COMPENSATED" in event_types


def test_saga_coordinator_duplicate_rejection():
    coordinator = SagaCoordinator()
    saga = SagaDefinition(saga_id="dummy", name="Dummy", steps=())
    coordinator.register_saga(saga)

    coordinator.start_saga("dummy", "exec-dup", "tenant-1", {})
    with pytest.raises(SagaCoordinatorError, match="Duplicate execution_id"):
        coordinator.start_saga("dummy", "exec-dup", "tenant-1", {})
