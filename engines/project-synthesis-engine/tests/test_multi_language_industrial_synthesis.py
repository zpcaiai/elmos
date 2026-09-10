"""Tests for End-to-End Multi-Language Enterprise Project Synthesis (Python, Go, TypeScript).
"""
from __future__ import annotations

import pytest

from elmos_project_synthesis.enterprise_go_target import generate_enterprise_go_files
from elmos_project_synthesis.enterprise_production_target import (
    generate_enterprise_python_files,
    generate_enterprise_target_files,
)
from elmos_project_synthesis.enterprise_typescript_target import generate_enterprise_typescript_files
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest


def _sample_synthesis_request(project_name: str = "order-platform") -> SynthesisRequest:
    draft = create_draft(
        name=project_name,
        description="Enterprise multi-language order platform",
        entity="order",
        languages=["python", "go", "typescript"],
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="release-admin@enterprise.org", approved_at="2026-09-10T00:00:00+00:00")
    return SynthesisRequest.from_mapping(approved)


def test_python_enterprise_synthesis_includes_ddd_and_workflow():
    req = _sample_synthesis_request()
    files = generate_enterprise_python_files(req)

    # Base enterprise files
    assert "main.py" in files or "src/main.py" in files
    assert "models.py" in files or "src/models.py" in files

    # Industrial DDD, FSM, and Distributed Tx files
    assert "src/domain/value_objects.py" in files
    assert "src/domain/events.py" in files
    assert "src/domain/aggregate.py" in files
    assert "src/workflow/fsm.py" in files
    assert "src/transactions/saga.py" in files
    assert "src/transactions/outbox.py" in files
    assert "src/transactions/lock.py" in files

    # Verify domain value objects content
    vo_content = files["src/domain/value_objects.py"]
    assert "class Money" in vo_content
    assert "class Address" in vo_content

    # Verify state machine content
    fsm_content = files["src/workflow/fsm.py"]
    assert "class OrderState" in fsm_content
    assert "class OrderStateMachine" in fsm_content
    assert "execute_transition" in fsm_content

    # Verify distributed transactions content
    tx_content = files["src/transactions/saga.py"]
    assert "class SagaOrchestrator" in tx_content
    assert "class SagaStepDef" in tx_content

    outbox_content = files["src/transactions/outbox.py"]
    assert "class OutboxDispatcher" in outbox_content


def test_go_enterprise_synthesis_includes_ddd_and_workflow():
    req = _sample_synthesis_request()
    files = generate_enterprise_go_files(req)

    # Base enterprise files
    assert "go.mod" in files
    assert "models/models.go" in files
    assert "outbox/outbox.go" in files
    assert "cache/cache.go" in files
    assert "api/handlers.go" in files
    assert "main.go" in files

    # Industrial Go DDD, FSM, and Distributed Tx files
    assert "domain/value_objects.go" in files
    assert "domain/events.go" in files
    assert "domain/aggregate.go" in files
    assert "workflow/fsm.go" in files
    assert "transactions/saga.go" in files
    assert "transactions/outbox.go" in files
    assert "transactions/lock.go" in files

    # Check Go value objects
    vo_code = files["domain/value_objects.go"]
    assert "type Money struct" in vo_code
    assert "type Address struct" in vo_code

    # Check Go state machine
    fsm_code = files["workflow/fsm.go"]
    assert "type OrderStateMachine struct" in fsm_code
    assert "sync.RWMutex" in fsm_code
    assert "ExecuteTransition" in fsm_code

    # Check Go distributed transactions
    saga_code = files["transactions/saga.go"]
    assert "type SagaOrchestrator" in saga_code or "type OrderSagaCoordinator" in saga_code
    outbox_code = files["transactions/outbox.go"]
    assert "type OutboxDispatcher struct" in outbox_code
    lock_code = files["transactions/lock.go"]
    assert "type DistributedLockManager struct" in lock_code


def test_typescript_enterprise_synthesis_includes_ddd_and_workflow():
    req = _sample_synthesis_request()
    files = generate_enterprise_typescript_files(req)

    # Base enterprise files
    assert "package.json" in files
    assert "src/app.module.ts" in files
    assert "src/main.ts" in files

    # Industrial TypeScript DDD, FSM, and Distributed Tx files
    assert "src/domain/value-objects.ts" in files
    assert "src/domain/events.ts" in files
    assert "src/domain/aggregate.ts" in files
    assert "src/workflow/fsm.service.ts" in files
    assert "src/transactions/saga.service.ts" in files
    assert "src/transactions/outbox.service.ts" in files
    assert "src/transactions/lock.service.ts" in files

    # Check TypeScript value objects
    vo_code = files["src/domain/value-objects.ts"]
    assert "export class Money" in vo_code
    assert "export class Address" in vo_code

    # Check TypeScript FSM
    fsm_code = files["src/workflow/fsm.service.ts"]
    assert "export class OrderStateMachineService" in fsm_code
    assert "executeTransition" in fsm_code

    # Check TypeScript Distributed Tx
    tx_code = files["src/transactions/saga.service.ts"]
    assert "export class OrderSagaService" in tx_code
    assert "execute" in tx_code

    outbox_code = files["src/transactions/outbox.service.ts"]
    assert "export class OutboxDispatcherService" in outbox_code

    lock_code = files["src/transactions/lock.service.ts"]
    assert "export class DistributedLockService" in lock_code
