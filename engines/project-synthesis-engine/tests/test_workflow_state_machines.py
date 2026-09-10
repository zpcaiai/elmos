"""Tests for Workflow State Machine Engine, Guards, Actions, and Audit Ledger.
"""
from __future__ import annotations

import pytest

from elmos_project_synthesis.workflow_state_machine import (
    EventSpec,
    FsmConcurrencyError,
    FsmGuardViolationError,
    IllegalStateTransitionError,
    StateMachineEngine,
    StateSpec,
    TransitionSpec,
    WorkflowFsmSpec,
)


def _sample_order_fsm() -> WorkflowFsmSpec:
    states = (
        StateSpec(name="DRAFT", is_initial=True),
        StateSpec(name="SUBMITTED"),
        StateSpec(name="PAID"),
        StateSpec(name="CANCELLED", is_terminal=True),
        StateSpec(name="FULFILLED", is_terminal=True),
    )
    events = (
        EventSpec(name="SUBMIT"),
        EventSpec(name="PAY"),
        EventSpec(name="CANCEL"),
        EventSpec(name="FULFILL"),
    )
    transitions = (
        TransitionSpec(
            from_state="DRAFT",
            event="SUBMIT",
            to_state="SUBMITTED",
            guard_rule_id="RULE-HAS-ITEMS",
        ),
        TransitionSpec(
            from_state="SUBMITTED",
            event="PAY",
            to_state="PAID",
            guard_rule_id="RULE-PAYMENT-OK",
        ),
        TransitionSpec(
            from_state="DRAFT",
            event="CANCEL",
            to_state="CANCELLED",
        ),
        TransitionSpec(
            from_state="SUBMITTED",
            event="CANCEL",
            to_state="CANCELLED",
        ),
        TransitionSpec(
            from_state="PAID",
            event="FULFILL",
            to_state="FULFILLED",
        ),
    )
    return WorkflowFsmSpec(
        name="OrderLifecycleFsm",
        entity_name="Order",
        states=states,
        events=events,
        transitions=transitions,
    )


def test_fsm_valid_transition_and_audit_log():
    fsm = _sample_order_fsm()
    engine = StateMachineEngine(fsm)

    # Register guards
    engine.register_guard("RULE-HAS-ITEMS", lambda st, pl: pl.get("item_count", 0) > 0)
    engine.register_guard("RULE-PAYMENT-OK", lambda st, pl: pl.get("payment_authorized", False) is True)

    entity_id = "ord-1001"
    current_state = "DRAFT"
    current_version = 1

    # Transition 1: DRAFT -> SUBMITTED
    new_state, new_version, log = engine.transition(
        entity_id=entity_id,
        current_state=current_state,
        current_version=current_version,
        event="SUBMIT",
        entity_state={"status": "DRAFT"},
        event_payload={"item_count": 3},
        actor="operator@enterprise.org",
    )

    assert new_state == "SUBMITTED"
    assert new_version == 2
    assert log.entity_name == "Order"
    assert log.from_state == "DRAFT"
    assert log.to_state == "SUBMITTED"
    assert log.actor == "operator@enterprise.org"

    # Transition 2: SUBMITTED -> PAID
    new_state2, new_version2, log2 = engine.transition(
        entity_id=entity_id,
        current_state=new_state,
        current_version=new_version,
        event="PAY",
        entity_state={"status": "SUBMITTED"},
        event_payload={"payment_authorized": True},
        actor="payment-gateway",
    )
    assert new_state2 == "PAID"
    assert new_version2 == 3


def test_fsm_invalid_transition_rejection():
    fsm = _sample_order_fsm()
    engine = StateMachineEngine(fsm)

    # Cannot jump DRAFT -> FULFILLED directly
    with pytest.raises(IllegalStateTransitionError) as exc:
        engine.transition(
            entity_id="ord-1002",
            current_state="DRAFT",
            current_version=1,
            event="FULFILL",
            entity_state={"status": "DRAFT"},
        )
    assert "cannot handle event 'FULFILL' in state 'DRAFT'" in str(exc.value)


def test_fsm_guard_condition_failure():
    fsm = _sample_order_fsm()
    engine = StateMachineEngine(fsm)
    engine.register_guard("RULE-HAS-ITEMS", lambda st, pl: pl.get("item_count", 0) > 0)

    # Guard fails when item_count is 0
    with pytest.raises(FsmGuardViolationError) as exc:
        engine.transition(
            entity_id="ord-1003",
            current_state="DRAFT",
            current_version=1,
            event="SUBMIT",
            entity_state={"status": "DRAFT"},
            event_payload={"item_count": 0},
        )
    assert "Guard violation [RULE-HAS-ITEMS]" in str(exc.value)


def test_fsm_optimistic_locking_conflict():
    fsm = _sample_order_fsm()
    engine = StateMachineEngine(fsm)

    # Expected version is 5, but current is 4 (stale write)
    with pytest.raises(FsmConcurrencyError) as exc:
        engine.transition(
            entity_id="ord-1004",
            current_state="DRAFT",
            current_version=4,
            event="CANCEL",
            entity_state={"status": "DRAFT"},
            expected_version=5,
        )
    assert "expected version 5, found 4" in str(exc.value)


def test_fsm_diagram_generation():
    fsm = _sample_order_fsm()
    mermaid = fsm.render_mermaid()
    assert "stateDiagram-v2" in mermaid
    assert "[*] --> DRAFT" in mermaid
    assert "DRAFT --> SUBMITTED : SUBMIT [RULE-HAS-ITEMS]" in mermaid
    assert "FULFILLED --> [*]" in mermaid

    plantuml = fsm.render_plantuml()
    assert "@startuml" in plantuml
    assert "@enduml" in plantuml
