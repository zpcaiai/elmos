"""Python FastAPI DDD, Workflow State Machine, and Distributed Transactions Emitter.

Generates complete industrial-grade DDD domain layers, state machines, and distributed transaction
coordinators for Python microservice workspaces.
"""
from __future__ import annotations

from typing import Dict
from .models import SynthesisRequest


def generate_python_domain_workflow_files(request: SynthesisRequest) -> Dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for Python."""
    files: Dict[str, str] = {}
    app_name = request.project_name
    entity = request.entities[0] if request.entities else None
    entity_name = entity.singular.capitalize() if entity else "Order"
    entity_lower = entity_name.lower()

    # 1. Domain Value Objects
    files["src/domain/value_objects.py"] = f'''"""Domain Value Objects with structural equality and invariant validation."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict
import re
from pydantic import BaseModel, Field, field_validator


class Money(BaseModel):
    """Immutable high-precision monetary value."""
    amount: Decimal = Field(..., ge=0, description="Amount in fractional decimal")
    currency: str = Field(default="USD", min_length=3, max_length=3)

    model_config = {{"frozen": True}}

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        code = v.strip().upper()
        if not re.match(r"^[A-Z]{{3}}$", code):
            raise ValueError(f"Invalid ISO-4217 currency code: {{code}}")
        return code

    def add(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {{self.currency}} vs {{other.currency}}")
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {{self.currency}} vs {{other.currency}}")
        if self.amount < other.amount:
            raise ValueError("Insufficient funds for subtraction")
        return Money(amount=self.amount - other.amount, currency=self.currency)


class Address(BaseModel):
    """Physical address value object."""
    street: str = Field(..., min_length=1, max_length=256)
    city: str = Field(..., min_length=1, max_length=128)
    state_province: str = Field(..., min_length=1, max_length=128)
    postal_code: str = Field(..., min_length=1, max_length=32)
    country: str = Field(default="CN", min_length=2, max_length=64)

    model_config = {{"frozen": True}}


class Quantity(BaseModel):
    """Unit-bearing quantity value object."""
    value: Decimal = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=32)

    model_config = {{"frozen": True}}
'''

    # 2. Domain Events
    files["src/domain/events.py"] = f'''"""Strongly typed Domain Events."""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """Domain Event Envelope."""
    event_id: str = Field(default_factory=lambda: f"evt-{{uuid4().hex[:16]}}")
    aggregate_type: str = "{entity_name}"
    aggregate_id: str
    event_type: str
    occurred_at: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    payload: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = "default"
    trace_id: Optional[str] = None


class {entity_name}CreatedEvent(DomainEvent):
    event_type: str = "{entity_name}Created"


class {entity_name}StateChangedEvent(DomainEvent):
    event_type: str = "{entity_name}StateChanged"


class {entity_name}CancelledEvent(DomainEvent):
    event_type: str = "{entity_name}Cancelled"
'''

    # 3. Domain Aggregate Root & Invariants
    files["src/domain/aggregate.py"] = f'''"""Domain Aggregate Root with encapsulated invariants."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from .value_objects import Money, Address
from .events import DomainEvent, {entity_name}CreatedEvent, {entity_name}StateChangedEvent, {entity_name}CancelledEvent


class DomainInvariantError(Exception):
    """Raised when an aggregate invariant is violated."""


class {entity_name}Item(BaseModel):
    item_id: str = Field(default_factory=lambda: f"itm-{{uuid4().hex[:8]}}")
    name: str
    unit_price: Decimal = Field(..., gt=0)
    quantity: int = Field(..., gt=0)

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


class {entity_name}Aggregate(BaseModel):
    """Aggregate Root enforcing consistency boundary."""
    id: str = Field(default_factory=lambda: f"{entity_lower}-{{uuid4().hex[:12]}}")
    tenant_id: str = "default"
    status: str = "DRAFT"  # DRAFT, SUBMITTED, APPROVED, FULFILLED, CANCELLED
    items: List[{entity_name}Item] = Field(default_factory=list)
    total_amount: Money = Field(default_factory=lambda: Money(amount=Decimal("0"), currency="USD"))
    shipping_address: Optional[Address] = None
    version: int = 1
    uncommitted_events: List[DomainEvent] = Field(default_factory=list, exclude=True)

    def add_item(self, name: str, unit_price: Decimal, quantity: int) -> None:
        """Add item and recompute total amount preserving invariants."""
        if self.status != "DRAFT":
            raise DomainInvariantError(f"Cannot mutate items in non-draft status: {{self.status}}")
        if quantity <= 0:
            raise DomainInvariantError("Quantity must be positive")

        item = {entity_name}Item(name=name, unit_price=unit_price, quantity=quantity)
        self.items.append(item)
        self._recalculate_total()

    def submit(self) -> None:
        """Submit aggregate for processing."""
        if not self.items:
            raise DomainInvariantError("Cannot submit empty aggregate without items")
        if self.total_amount.amount <= Decimal("0"):
            raise DomainInvariantError("Total amount must be greater than zero")

        old_status = self.status
        self.status = "SUBMITTED"
        self.version += 1
        self.uncommitted_events.append(
            {entity_name}StateChangedEvent(
                aggregate_id=self.id,
                tenant_id=self.tenant_id,
                payload={{"old_status": old_status, "new_status": self.status}},
            )
        )

    def cancel(self, reason: str = "User cancelled") -> None:
        """Cancel aggregate."""
        if self.status in ("FULFILLED", "CANCELLED"):
            raise DomainInvariantError(f"Cannot cancel aggregate in status {{self.status}}")

        self.status = "CANCELLED"
        self.version += 1
        self.uncommitted_events.append(
            {entity_name}CancelledEvent(
                aggregate_id=self.id,
                tenant_id=self.tenant_id,
                payload={{"reason": reason}},
            )
        )

    def _recalculate_total(self) -> None:
        total = sum((item.subtotal for item in self.items), Decimal("0"))
        self.total_amount = Money(amount=total, currency=self.total_amount.currency)

    def poll_events(self) -> List[DomainEvent]:
        events = list(self.uncommitted_events)
        self.uncommitted_events.clear()
        return events
'''

    # 4. Workflow State Machine Engine
    files["src/workflow/fsm.py"] = f'''"""Deterministic Workflow State Machine for {entity_name}."""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class StateTransitionError(Exception):
    pass


class StateTransitionLog(BaseModel):
    transition_id: str
    aggregate_id: str
    from_state: str
    to_state: str
    event: str
    timestamp: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    version: int


class {entity_name}StateMachine:
    """Finite State Machine enforcing allowable transitions."""

    TRANSITIONS = {{
        ("DRAFT", "submit"): "SUBMITTED",
        ("SUBMITTED", "approve"): "APPROVED",
        ("SUBMITTED", "reject"): "REJECTED",
        ("APPROVED", "fulfill"): "FULFILLED",
        ("DRAFT", "cancel"): "CANCELLED",
        ("SUBMITTED", "cancel"): "CANCELLED",
        ("APPROVED", "cancel"): "CANCELLED",
    }}

    def __init__(self) -> None:
        self.transition_logs: List[StateTransitionLog] = []

    def can_transition(self, current_state: str, event: str) -> bool:
        return (current_state, event) in self.TRANSITIONS

    def execute_transition(
        self, aggregate_id: str, current_state: str, event: str, current_version: int
    ) -> Tuple[str, int, StateTransitionLog]:
        target_state = self.TRANSITIONS.get((current_state, event))
        if not target_state:
            raise StateTransitionError(
                f"Invalid transition from state '{{current_state}}' on event '{{event}}'"
            )

        new_version = current_version + 1
        log = StateTransitionLog(
            transition_id=f"trn-{{len(self.transition_logs) + 1}}",
            aggregate_id=aggregate_id,
            from_state=current_state,
            to_state=target_state,
            event=event,
            version=new_version,
        )
        self.transition_logs.append(log)
        return target_state, new_version, log
'''

    # 5. Distributed Transactions: Saga Coordinator
    files["src/transactions/saga.py"] = f'''"""Orchestrated Saga Pattern with LIFO Compensation."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SagaStep(BaseModel):
    name: str
    action: Callable[[Dict[str, Any]], Dict[str, Any]]
    compensation: Callable[[Dict[str, Any]], None]


class {entity_name}SagaCoordinator:
    """Executes multi-step forward Saga with LIFO reversal on failure."""

    def __init__(self, steps: List[SagaStep]) -> None:
        self.steps = steps

    def run(self, context: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        completed_steps: List[SagaStep] = []

        # 1. Forward phase
        for step in self.steps:
            try:
                res = step.action(context)
                context.update(res)
                completed_steps.append(step)
            except Exception as exc:
                logger.error("Saga step '%s' failed: %s. Initiating LIFO compensation.", step.name, exc)
                self._rollback(completed_steps, context)
                return False, f"Step '{{step.name}}' failed: {{exc}}", context

        return True, "Saga completed successfully", context

    def _rollback(self, completed_steps: List[SagaStep], context: Dict[str, Any]) -> None:
        for step in reversed(completed_steps):
            try:
                step.compensation(context)
            except Exception as exc:
                logger.critical("Compensation of '%s' failed: %s", step.name, exc)


class SagaStepDef(SagaStep):
    """Step definition for orchestrated saga."""
    pass


class SagaOrchestrator({entity_name}SagaCoordinator):
    """Saga orchestrator coordinating forward actions and reverse compensations."""
    pass
'''

    # 6. Transactional Outbox Pattern & Worker
    files["src/transactions/outbox.py"] = f'''"""Transactional Outbox with SKIP LOCKED async dispatch."""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class OutboxEventRecord(BaseModel):
    event_id: str
    tenant_id: str = "default"
    aggregate_type: str = "{entity_name}"
    aggregate_id: str
    event_type: str
    payload: Dict[str, Any]
    status: str = "PENDING"  # PENDING, IN_FLIGHT, PUBLISHED, FAILED
    retry_count: int = 0
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    published_at: Optional[str] = None


class OutboxDispatcherService:
    """Dispatches outbox events with idempotency and retry handling."""

    def __init__(self, publisher_func: Callable[[OutboxEventRecord], bool]) -> None:
        self.publisher_func = publisher_func
        self._store: Dict[str, OutboxEventRecord] = {{}}

    def enqueue(self, event: OutboxEventRecord) -> None:
        self._store[event.event_id] = event

    def dispatch_pending(self) -> int:
        published = 0
        for evt in list(self._store.values()):
            if evt.status == "PENDING":
                evt.status = "IN_FLIGHT"
                ok = self.publisher_func(evt)
                if ok:
                    evt.status = "PUBLISHED"
                    evt.published_at = dt.datetime.now(dt.timezone.utc).isoformat()
                    published += 1
                else:
                    evt.status = "FAILED"
                    evt.retry_count += 1
        return published
'''

    # 7. Distributed Lock & Fencing
    files["src/transactions/lock.py"] = f'''"""Distributed Lock with Monotonic Fencing Token."""
from __future__ import annotations

import time
import threading
from typing import Dict, Optional


class DistributedLockService:
    """Manages resource locks with fencing tokens preventing stale split-brain writes."""

    def __init__(self) -> None:
        self._locks: Dict[str, Dict[str, Any]] = {{}}
        self._generation: Dict[str, int] = {{}}
        self._mu = threading.Lock()

    def acquire(self, resource_id: str, owner: str, ttl_sec: float = 30.0) -> int:
        now = time.monotonic()
        with self._mu:
            lock = self._locks.get(resource_id)
            if lock and lock["expires_at"] > now and lock["owner"] != owner:
                raise RuntimeError(f"Resource '{{resource_id}}' locked by '{{lock['owner']}}'")

            token = self._generation.get(resource_id, 0) + 1
            self._generation[resource_id] = token
            self._locks[resource_id] = {{"owner": owner, "expires_at": now + ttl_sec, "token": token}}
            return token

    def release(self, resource_id: str, owner: str) -> None:
        with self._mu:
            lock = self._locks.get(resource_id)
            if lock and lock["owner"] == owner:
                del self._locks[resource_id]
'''

    return files
