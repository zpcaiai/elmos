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


def test_java_enterprise_synthesis_includes_ddd_and_workflow():
    from elmos_project_synthesis.enterprise_java_target import generate_enterprise_java_files

    req = _sample_synthesis_request()
    files = generate_enterprise_java_files(req)

    # Base enterprise files
    assert "pom.xml" in files
    assert any("Application.java" in k for k in files)

    # Industrial Java DDD, FSM, and Distributed Tx files
    assert any("domain/Money.java" in k for k in files)
    assert any("domain/Address.java" in k for k in files)
    assert any("domain/DomainEvent.java" in k for k in files)
    assert any("domain/OrderAggregate.java" in k for k in files)
    assert any("workflow/OrderStateMachine.java" in k for k in files)
    assert any("transactions/SagaOrchestrator.java" in k for k in files)
    assert any("transactions/DistributedLockManager.java" in k for k in files)

    money_file = [v for k, v in files.items() if k.endswith("domain/Money.java")][0]
    assert "public record Money" in money_file
    assert "add(Money other)" in money_file

    fsm_file = [v for k, v in files.items() if k.endswith("workflow/OrderStateMachine.java")][0]
    assert "public class OrderStateMachine" in fsm_file
    assert "State transition(" in fsm_file

    saga_file = [v for k, v in files.items() if k.endswith("transactions/SagaOrchestrator.java")][0]
    assert "public class SagaOrchestrator" in saga_file
    assert "rollback(" in saga_file


def test_dotnet_enterprise_synthesis_includes_ddd_and_workflow():
    from elmos_project_synthesis.enterprise_dotnet_target import generate_enterprise_dotnet_files

    req = _sample_synthesis_request()
    files = generate_enterprise_dotnet_files(req)

    # Base enterprise files
    assert "Program.cs" in files
    assert any(k.endswith(".csproj") for k in files)

    # Industrial .NET DDD, FSM, and Distributed Tx files
    assert "Domain/ValueObjects.cs" in files
    assert "Domain/DomainEvents.cs" in files
    assert "Domain/OrderAggregate.cs" in files
    assert "Workflow/OrderStateMachine.cs" in files
    assert "Transactions/SagaOrchestrator.cs" in files
    assert "Transactions/DistributedLockManager.cs" in files

    vo_code = files["Domain/ValueObjects.cs"]
    assert "public readonly record struct Money" in vo_code
    assert "public record Address" in vo_code

    fsm_code = files["Workflow/OrderStateMachine.cs"]
    assert "public class OrderStateMachine" in fsm_code
    assert "public State Transition(" in fsm_code

    saga_code = files["Transactions/SagaOrchestrator.cs"]
    assert "public class SagaOrchestrator" in saga_code
    assert "RollbackAsync" in saga_code


def test_rust_enterprise_synthesis_includes_ddd_and_workflow():
    from elmos_project_synthesis.enterprise_polyglot_targets import generate_enterprise_rust_files

    req = _sample_synthesis_request()
    files = generate_enterprise_rust_files(req)

    # Base enterprise files
    assert "Cargo.toml" in files
    assert "src/main.rs" in files

    # Industrial Rust DDD, FSM, and Distributed Tx files
    assert "src/domain/value_objects.rs" in files
    assert "src/domain/events.rs" in files
    assert "src/domain/aggregate.rs" in files
    assert "src/workflow/fsm.rs" in files
    assert "src/transactions/saga.rs" in files
    assert "src/transactions/lock.rs" in files

    vo_code = files["src/domain/value_objects.rs"]
    assert "pub struct Money" in vo_code
    assert "pub fn add(" in vo_code

    fsm_code = files["src/workflow/fsm.rs"]
    assert "pub enum State" in fsm_code
    assert "pub struct StateMachine" in fsm_code

    saga_code = files["src/transactions/saga.rs"]
    assert "pub struct SagaOrchestrator" in saga_code
    assert "pub async fn execute(" in saga_code


def test_kotlin_enterprise_synthesis_includes_ddd_and_workflow():
    from elmos_project_synthesis.enterprise_polyglot_targets import generate_enterprise_kotlin_files

    req = _sample_synthesis_request()
    files = generate_enterprise_kotlin_files(req)

    assert "build.gradle.kts" in files
    assert any("domain/ValueObjects.kt" in k for k in files)
    assert any("domain/DomainEvent.kt" in k for k in files)
    assert any("domain/OrderAggregate.kt" in k for k in files)
    assert any("workflow/OrderStateMachine.kt" in k for k in files)
    assert any("transactions/SagaOrchestrator.kt" in k for k in files)
    assert any("transactions/DistributedLockManager.kt" in k for k in files)


def test_php_enterprise_synthesis_includes_ddd_and_workflow():
    from elmos_project_synthesis.enterprise_polyglot_targets import generate_enterprise_php_files

    req = _sample_synthesis_request()
    files = generate_enterprise_php_files(req)

    assert "composer.json" in files
    assert "app/Domain/ValueObjects/Money.php" in files
    assert "app/Domain/ValueObjects/Address.php" in files
    assert "app/Domain/Entities/OrderAggregate.php" in files
    assert "app/Workflow/OrderStateMachine.php" in files
    assert "app/Transactions/SagaOrchestrator.php" in files
    assert "app/Transactions/DistributedLockManager.php" in files

    money_code = files["app/Domain/ValueObjects/Money.php"]
    assert "final readonly class Money" in money_code

    fsm_code = files["app/Workflow/OrderStateMachine.php"]
    assert "class OrderStateMachine" in fsm_code


def test_all_8_languages_via_enterprise_target_router():
    from elmos_project_synthesis.enterprise_production_target import generate_enterprise_target_files

    req = _sample_synthesis_request()
    for lang in ["python", "go", "typescript", "java", "csharp", "rust", "kotlin", "php"]:
        generated = generate_enterprise_target_files(req, language=lang)
        assert len(generated) > 5, f"Target {lang} produced too few files ({len(generated)})"
        # Check that each language has at least one domain or value object file
        has_domain = any("domain" in k.lower() for k in generated.keys())
        assert has_domain, f"Target {lang} missing domain models!"
