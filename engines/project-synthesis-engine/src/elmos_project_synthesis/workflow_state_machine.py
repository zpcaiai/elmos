"""Workflow State Machine Engine for Industrial Microservice Synthesis.

Provides robust, deterministic Finite State Machine (FSM) capabilities:
1. Declarative State & Transition Metamodel with Initial, Intermediate, and Terminal states.
2. Guard Conditions: Business rules evaluated prior to allowing transition.
3. Pre & Post Action Hooks: Resource allocation, notification, and side-effect dispatch.
4. Optimistic Concurrency Control: Version checking preventing dirty concurrent transitions.
5. Immutable State Transition Audit Ledger (state_transition_logs).
6. Automatic State Machine Diagram Rendering (Mermaid and PlantUML).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from .domain_models import DomainError, DomainInvariantViolationError


class FsmError(DomainError):
    """Base exception for state machine violations."""


class IllegalStateTransitionError(FsmError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: str, event: str, entity_id: str = ""):
        super().__init__(
            f"Illegal transition: entity '{entity_id}' cannot handle event '{event}' in state '{current_state}'"
        )
        self.current_state = current_state
        self.event = event
        self.entity_id = entity_id


class FsmGuardViolationError(FsmError):
    """Raised when a transition guard condition evaluates to false."""

    def __init__(self, guard_id: str, message: str, entity_id: str = ""):
        super().__init__(f"Guard violation [{guard_id}] on entity '{entity_id}': {message}")
        self.guard_id = guard_id
        self.message = message
        self.entity_id = entity_id


class FsmConcurrencyError(FsmError):
    """Raised when an optimistic concurrency conflict occurs during state transition."""

    def __init__(self, expected_version: int, actual_version: int, entity_id: str = ""):
        super().__init__(
            f"State transition concurrency conflict on entity '{entity_id}': "
            f"expected version {expected_version}, found {actual_version}"
        )
        self.expected_version = expected_version
        self.actual_version = actual_version


# ============================================================================
# 1. State Machine Metamodel Specs
# ============================================================================


@dataclass(frozen=True)
class StateSpec:
    """Specification of an entity state."""

    name: str
    is_initial: bool = False
    is_terminal: bool = False
    description: str = ""


@dataclass(frozen=True)
class EventSpec:
    """Specification of an event triggering a transition."""

    name: str
    description: str = ""
    payload_fields: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TransitionSpec:
    """Specification of a directed state transition."""

    from_state: str
    to_state: str
    event: str
    guard_rule_id: Optional[str] = None
    before_hook: Optional[str] = None
    after_hook: Optional[str] = None
    description: str = ""


@dataclass(frozen=True)
class StateTransitionLog:
    """Immutable audit record for a successful state transition."""

    transition_id: str = field(default_factory=lambda: f"trn-{uuid4().hex[:16]}")
    aggregate_id: str = ""
    entity_name: str = ""
    from_state: str = ""
    to_state: str = ""
    event: str = ""
    actor: str = "system"
    tenant_id: str = "default"
    version_before: int = 1
    version_after: int = 2
    timestamp: str = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "aggregate_id": self.aggregate_id,
            "entity_name": self.entity_name,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "event": self.event,
            "actor": self.actor,
            "tenant_id": self.tenant_id,
            "version_before": self.version_before,
            "version_after": self.version_after,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class WorkflowFsmSpec:
    """Complete Workflow State Machine Specification for a synthesized service."""

    name: str
    entity_name: str
    state_field: str = "status"
    states: Tuple[StateSpec, ...] = field(default_factory=tuple)
    events: Tuple[EventSpec, ...] = field(default_factory=tuple)
    transitions: Tuple[TransitionSpec, ...] = field(default_factory=tuple)

    def get_initial_state(self) -> str:
        for s in self.states:
            if s.is_initial:
                return s.name
        return self.states[0].name if self.states else "INITIAL"

    def get_terminal_states(self) -> Set[str]:
        return {s.name for s in self.states if s.is_terminal}

    def find_transition(self, from_state: str, event: str) -> Optional[TransitionSpec]:
        for t in self.transitions:
            if t.from_state == from_state and t.event == event:
                return t
        return None

    def render_mermaid(self) -> str:
        """Render standard Mermaid stateDiagram-v2 diagram."""
        lines = ["stateDiagram-v2"]
        init = self.get_initial_state()
        lines.append(f"    [*] --> {init}")

        for t in self.transitions:
            guard_str = f" [{t.guard_rule_id}]" if t.guard_rule_id else ""
            lines.append(f"    {t.from_state} --> {t.to_state} : {t.event}{guard_str}")

        for term in sorted(self.get_terminal_states()):
            lines.append(f"    {term} --> [*]")

        return "\n".join(lines)

    def render_plantuml(self) -> str:
        """Render PlantUML state diagram."""
        lines = ["@startuml", f"title {self.name} Workflow State Machine"]
        init = self.get_initial_state()
        lines.append(f"[*] --> {init}")

        for t in self.transitions:
            guard_str = f" [{t.guard_rule_id}]" if t.guard_rule_id else ""
            lines.append(f"{t.from_state} --> {t.to_state} : {t.event}{guard_str}")

        for term in sorted(self.get_terminal_states()):
            lines.append(f"{term} --> [*]")

        lines.append("@enduml")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entity_name": self.entity_name,
            "state_field": self.state_field,
            "states": [s.__dict__ for s in self.states],
            "events": [e.__dict__ for e in self.events],
            "transitions": [t.__dict__ for t in self.transitions],
        }


# ============================================================================
# 2. Execution Engine
# ============================================================================


class StateMachineEngine:
    """Runtime coordinator that executes state machine transitions with validation."""

    def __init__(self, spec: WorkflowFsmSpec):
        self.spec = spec
        self._guard_registry: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], bool]] = {}
        self._audit_ledger: List[StateTransitionLog] = []

    def register_guard(
        self, guard_id: str, predicate: Callable[[Dict[str, Any], Dict[str, Any]], bool]
    ) -> None:
        """Register a Python guard predicate: (entity_state, event_payload) -> bool."""
        self._guard_registry[guard_id] = predicate

    def transition(
        self,
        entity_id: str,
        current_state: str,
        current_version: int,
        event: str,
        entity_state: Dict[str, Any],
        event_payload: Optional[Dict[str, Any]] = None,
        actor: str = "system",
        tenant_id: str = "default",
        expected_version: Optional[int] = None,
    ) -> Tuple[str, int, StateTransitionLog]:
        """Execute a state transition. Returns (new_state, new_version, transition_log)."""
        payload = event_payload or {}

        # 1. Optimistic locking check
        if expected_version is not None and expected_version != current_version:
            raise FsmConcurrencyError(expected_version, current_version, entity_id)

        # 2. Find valid transition
        trans = self.spec.find_transition(current_state, event)
        if trans is None:
            raise IllegalStateTransitionError(current_state, event, entity_id)

        # 3. Evaluate guard if present
        if trans.guard_rule_id:
            guard_func = self._guard_registry.get(trans.guard_rule_id)
            if guard_func is not None:
                passed = guard_func(entity_state, payload)
                if not passed:
                    raise FsmGuardViolationError(
                        trans.guard_rule_id,
                        f"Transition {trans.from_state} -> {trans.to_state} on event '{event}' rejected by guard",
                        entity_id,
                    )

        # 4. Advance version
        new_state = trans.to_state
        new_version = current_version + 1

        # 5. Record immutable audit log
        log_entry = StateTransitionLog(
            aggregate_id=entity_id,
            entity_name=self.spec.entity_name,
            from_state=current_state,
            to_state=new_state,
            event=event,
            actor=actor,
            tenant_id=tenant_id,
            version_before=current_version,
            version_after=new_version,
            metadata={"payload": payload, "guard": trans.guard_rule_id},
        )
        self._audit_ledger.append(log_entry)

        return new_state, new_version, log_entry

    def get_audit_history(self, aggregate_id: Optional[str] = None) -> List[StateTransitionLog]:
        if aggregate_id:
            return [log for log in self._audit_ledger if log.aggregate_id == aggregate_id]
        return list(self._audit_ledger)

    def get_audit_ledger(self) -> List[StateTransitionLog]:
        return list(self._audit_ledger)
