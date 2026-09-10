"""Domain-Driven Design (DDD) Core Engine for Industrial Project Synthesis.

Provides enterprise-grade domain modeling capabilities:
1. Value Objects: Immutable, self-validating, structurally equal value types
   (Money, Address, GeoLocation, Email, Quantity, DateRange, and custom specs).
2. Aggregates and Aggregate Roots: Transaction and consistency boundaries encapsulating
   entities and value objects, exposing rich business methods and protecting invariants.
3. Domain Events: Strongly typed event envelope recorded during state changes and
   dispatched to transactional outbox or message buses.
4. Business Invariant Engine: Real-time validation of business rules and invariants
   with fail-closed domain exceptions.
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
CURRENCY_REGEX = re.compile(r"^[A-Z]{3}$")


class DomainError(Exception):
    """Base exception for all domain logic violations."""


class DomainInvariantViolationError(DomainError):
    """Raised when an aggregate invariant is violated."""

    def __init__(self, rule_id: str, message: str, aggregate_id: Optional[str] = None):
        super().__init__(f"[{rule_id}] Aggregate {aggregate_id or 'unknown'}: {message}")
        self.rule_id = rule_id
        self.message = message
        self.aggregate_id = aggregate_id


# ============================================================================
# 1. Built-in and Custom Value Objects
# ============================================================================


@dataclass(frozen=True)
class ValueObject:
    """Base immutable Value Object providing structural equality and validation."""

    def validate(self) -> None:
        """Validate invariant constraints. Subclasses must override."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize value object to dictionary."""
        return {
            key: str(value) if isinstance(value, (Decimal, dt.datetime, dt.date)) else value
            for key, value in self.__dict__.items()
        }


@dataclass(frozen=True)
class Money(ValueObject):
    """Industrial-grade Money value object with high-precision decimal arithmetic."""

    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(self, "currency", self.currency.strip().upper())
        self.validate()

    def validate(self) -> None:
        if not CURRENCY_REGEX.match(self.currency):
            raise DomainInvariantViolationError(
                "MONEY_INVALID_CURRENCY", f"Invalid ISO 4217 currency code: {self.currency}"
            )

    def add(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise DomainInvariantViolationError(
                "MONEY_CURRENCY_MISMATCH",
                f"Cannot add different currencies: {self.currency} and {other.currency}",
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise DomainInvariantViolationError(
                "MONEY_CURRENCY_MISMATCH",
                f"Cannot subtract different currencies: {self.currency} and {other.currency}",
            )
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def multiply(self, factor: Decimal | int | float) -> Money:
        f = Decimal(str(factor))
        return Money(amount=self.amount * f, currency=self.currency)

    def is_positive(self) -> bool:
        return self.amount > Decimal("0")

    def is_negative(self) -> bool:
        return self.amount < Decimal("0")

    def is_zero(self) -> bool:
        return self.amount == Decimal("0")


@dataclass(frozen=True)
class Address(ValueObject):
    """Physical mailing / billing address value object."""

    street: str
    city: str
    state_province: str
    postal_code: str
    country: str = "CN"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.street or not self.street.strip():
            raise DomainInvariantViolationError("ADDRESS_EMPTY_STREET", "Street cannot be empty")
        if not self.city or not self.city.strip():
            raise DomainInvariantViolationError("ADDRESS_EMPTY_CITY", "City cannot be empty")
        if not self.postal_code or not self.postal_code.strip():
            raise DomainInvariantViolationError("ADDRESS_EMPTY_POSTAL_CODE", "Postal code cannot be empty")


@dataclass(frozen=True)
class GeoLocation(ValueObject):
    """Geographic WGS-84 coordinate value object."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not (-90.0 <= self.latitude <= 90.0):
            raise DomainInvariantViolationError(
                "GEO_INVALID_LATITUDE", f"Latitude {self.latitude} outside valid range [-90, 90]"
            )
        if not (-180.0 <= self.longitude <= 180.0):
            raise DomainInvariantViolationError(
                "GEO_INVALID_LONGITUDE", f"Longitude {self.longitude} outside valid range [-180, 180]"
            )


@dataclass(frozen=True)
class Email(ValueObject):
    """Electronic mail address value object."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        object.__setattr__(self, "value", normalized)
        self.validate()

    def validate(self) -> None:
        if not EMAIL_REGEX.match(self.value):
            raise DomainInvariantViolationError("EMAIL_FORMAT_INVALID", f"Invalid email format: {self.value}")


@dataclass(frozen=True)
class Quantity(ValueObject):
    """Measured quantity with physical/business units."""

    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            object.__setattr__(self, "value", Decimal(str(self.value)))
        object.__setattr__(self, "unit", self.unit.strip().lower())
        self.validate()

    def validate(self) -> None:
        if not self.unit:
            raise DomainInvariantViolationError("QUANTITY_UNIT_EMPTY", "Unit cannot be empty")


@dataclass(frozen=True)
class DateRange(ValueObject):
    """Time interval value object with boundary validation."""

    start_date: dt.date
    end_date: dt.date

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.start_date > self.end_date:
            raise DomainInvariantViolationError(
                "DATE_RANGE_INVERTED",
                f"Start date {self.start_date} cannot be after end date {self.end_date}",
            )

    def contains(self, target: dt.date) -> bool:
        return self.start_date <= target <= self.end_date


# ============================================================================
# 2. Domain Events
# ============================================================================


@dataclass(frozen=True)
class DomainEvent:
    """Strongly typed Domain Event envelope."""

    event_id: str = field(default_factory=lambda: f"evt-{uuid4().hex[:16]}")
    aggregate_type: str = "Aggregate"
    aggregate_id: str = ""
    event_type: str = "DomainEvent"
    occurred_at: str = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    tenant_id: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
        }


# ============================================================================
# 3. Invariant Rule Specification & Evaluator
# ============================================================================


@dataclass(frozen=True)
class InvariantRuleSpec:
    """Specification of a declarative business invariant."""

    rule_id: str
    description: str
    target_field: str
    operator: str  # gte, gt, lte, lt, eq, neq, not_null, in_set, regex
    expected_value: Any
    error_message: str


class InvariantEvaluator:
    """Evaluates declarative invariant rules against aggregate state."""

    @staticmethod
    def evaluate(rule: InvariantRuleSpec, target_data: Dict[str, Any], aggregate_id: str = "") -> None:
        val = target_data.get(rule.target_field)
        op = rule.operator

        if op == "not_null":
            if val is None:
                raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
            return

        if val is None:
            return  # Null checks handled by not_null

        if op in ("gte", "gt", "lte", "lt", "eq", "neq"):
            try:
                num_val = Decimal(str(val))
                exp_val = Decimal(str(rule.expected_value))
                if op == "gte" and not (num_val >= exp_val):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
                elif op == "gt" and not (num_val > exp_val):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
                elif op == "lte" and not (num_val <= exp_val):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
                elif op == "lt" and not (num_val < exp_val):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
                elif op == "eq" and not (num_val == exp_val):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
                elif op == "neq" and not (num_val != exp_val):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)
            except (decimal.InvalidOperation, ValueError) as exc:
                if op == "eq" and str(val) != str(rule.expected_value):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id) from exc
                elif op == "neq" and str(val) == str(rule.expected_value):
                    raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id) from exc

        elif op == "in_set":
            allowed = set(rule.expected_value if isinstance(rule.expected_value, list) else [rule.expected_value])
            if val not in allowed:
                raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)

        elif op == "regex":
            pattern = re.compile(str(rule.expected_value))
            if not pattern.match(str(val)):
                raise DomainInvariantViolationError(rule.rule_id, rule.error_message, aggregate_id)


# ============================================================================
# 4. Aggregate Root Model
# ============================================================================


class AggregateRoot:
    """Base class for Aggregate Roots with domain event queue & invariant enforcement."""

    def __init__(self, aggregate_id: str, tenant_id: str = "default"):
        self.id = aggregate_id
        self.tenant_id = tenant_id
        self.version: int = 1
        self._uncommitted_events: List[DomainEvent] = []
        self._invariants: List[InvariantRuleSpec] = []

    def register_invariant(self, rule: InvariantRuleSpec) -> None:
        self._invariants.append(rule)

    def check_invariants(self, state_dict: Dict[str, Any]) -> None:
        for rule in self._invariants:
            InvariantEvaluator.evaluate(rule, state_dict, self.id)

    def record_event(self, event_type: str, payload: Dict[str, Any], trace_id: Optional[str] = None) -> DomainEvent:
        event = DomainEvent(
            aggregate_type=self.__class__.__name__,
            aggregate_id=self.id,
            event_type=event_type,
            payload=payload,
            trace_id=trace_id,
            tenant_id=self.tenant_id,
        )
        self._uncommitted_events.append(event)
        return event

    def poll_uncommitted_events(self) -> List[DomainEvent]:
        events = list(self._uncommitted_events)
        self._uncommitted_events.clear()
        return events

    def has_uncommitted_events(self) -> bool:
        return len(self._uncommitted_events) > 0


# ============================================================================
# 5. Domain Model Specification for Project Synthesis
# ============================================================================


@dataclass(frozen=True)
class ValueObjectFieldSpec:
    name: str
    type: str  # string, integer, number, boolean, decimal
    required: bool = True
    default: Optional[Any] = None


@dataclass(frozen=True)
class CustomValueObjectSpec:
    """Definition of a project-specific Value Object."""

    name: str
    fields: Tuple[ValueObjectFieldSpec, ...]
    validation_rules: Tuple[InvariantRuleSpec, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "fields": [f.__dict__ for f in self.fields],
            "validation_rules": [r.__dict__ for r in self.validation_rules],
        }


@dataclass(frozen=True)
class DomainMethodSpec:
    """Specification of a rich domain behavior method on an aggregate."""

    name: str
    description: str
    parameters: Tuple[Tuple[str, str], ...]  # (param_name, param_type)
    state_mutations: Dict[str, str]  # field -> new_value_expression
    emitted_event_type: Optional[str] = None
    guard_rule_ids: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AggregateModelSpec:
    """Complete Specification for a Domain Aggregate in SynthesisRequest."""

    name: str
    root_entity: str
    child_entities: Tuple[str, ...] = field(default_factory=tuple)
    value_objects: Tuple[str, ...] = field(default_factory=tuple)
    invariants: Tuple[InvariantRuleSpec, ...] = field(default_factory=tuple)
    methods: Tuple[DomainMethodSpec, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "root_entity": self.root_entity,
            "child_entities": list(self.child_entities),
            "value_objects": list(self.value_objects),
            "invariants": [r.__dict__ for r in self.invariants],
            "methods": [
                {
                    "name": m.name,
                    "description": m.description,
                    "parameters": list(m.parameters),
                    "state_mutations": m.state_mutations,
                    "emitted_event_type": m.emitted_event_type,
                    "guard_rule_ids": list(m.guard_rule_ids),
                }
                for m in self.methods
            ],
        }
