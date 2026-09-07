from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Any, Callable


class AuthorizationError(PermissionError):
    pass


class StaleFenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    role: str


def authorize(principal: Principal, resource_tenant: str, action: str) -> bool:
    if principal.tenant_id != resource_tenant:
        raise AuthorizationError("cross-tenant access denied")
    allowed = {
        "viewer": {"read"},
        "developer": {"read", "execute"},
        "owner": {"read", "execute", "admin", "billing"},
    }
    if action not in allowed.get(principal.role, set()):
        raise AuthorizationError("role lacks permission")
    return True


VALID_TRANSITIONS = {
    "PLANNED": {"PREPARING", "CANCELLED"},
    "PREPARING": {"RUNNING", "FAILED", "CANCELLED"},
    "RUNNING": {"PAUSED", "COMPLETED", "FAILED", "CANCELLED"},
    "PAUSED": {"RUNNING", "CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}


@dataclass
class ControlPlaneRun:
    state: str = "PLANNED"
    revision: int = 0
    terminal_receipt: str | None = None

    def transition(self, target: str, expected_revision: int) -> None:
        if expected_revision != self.revision:
            raise RuntimeError("compare-and-swap revision mismatch")
        if target not in VALID_TRANSITIONS[self.state]:
            raise RuntimeError(f"invalid transition {self.state}->{target}")
        self.state = target
        self.revision += 1

    def complete(self, receipt: str, expected_revision: int) -> None:
        if self.state == "COMPLETED" and self.terminal_receipt == receipt:
            return
        self.transition("COMPLETED", expected_revision)
        self.terminal_receipt = receipt


@dataclass
class UsageLedger:
    events: dict[str, Decimal] = field(default_factory=dict)

    def record(self, event_id: str, amount: Decimal) -> bool:
        if event_id in self.events:
            return False
        self.events[event_id] = amount
        return True

    @property
    def total(self) -> Decimal:
        return sum(self.events.values(), Decimal("0"))


def route_model(
    providers: list[tuple[str, Callable[[], str]]], ledger: UsageLedger, request_id: str
) -> tuple[str, str]:
    failures: list[str] = []
    for provider_name, call in providers:
        try:
            output = call()
            ledger.record(f"{request_id}:{provider_name}", Decimal("1"))
            return provider_name, output
        except Exception as exc:  # reference fixture intentionally provider-neutral
            failures.append(f"{provider_name}:{type(exc).__name__}")
    raise RuntimeError("all providers failed: " + ",".join(failures))


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    score: float


def grounded_answer(question: str, chunks: list[Chunk], threshold: float = 0.8) -> dict[str, Any]:
    relevant = [chunk for chunk in chunks if chunk.score >= threshold]
    if not relevant:
        return {"answer": None, "status": "insufficient-evidence", "citations": []}
    selected = relevant[0]
    return {
        "answer": f"Grounded answer for: {question}",
        "status": "grounded",
        "citations": [{"chunk_id": selected.chunk_id, "quote_hash": sha256(selected.text.encode()).hexdigest()}],
    }


@dataclass(frozen=True)
class EvidenceFact:
    claim: str
    confidence: str
    file: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    def validate(self) -> None:
        if self.confidence == "confirmed":
            if not self.file or not self.start_line or not self.end_line:
                raise ValueError("confirmed claim requires file and line evidence")
            if self.end_line < self.start_line:
                raise ValueError("invalid evidence range")


@dataclass
class Wallet:
    balance: Decimal
    reserved: dict[str, Decimal] = field(default_factory=dict)
    consumed: dict[str, Decimal] = field(default_factory=dict)

    def reserve(self, reservation_id: str, amount: Decimal) -> bool:
        if reservation_id in self.reserved or reservation_id in self.consumed:
            return False
        available = self.balance - sum(self.reserved.values(), Decimal("0"))
        if amount <= 0 or amount > available:
            raise ValueError("insufficient or invalid credit")
        self.reserved[reservation_id] = amount
        return True

    def consume(self, reservation_id: str, usage_id: str, amount: Decimal) -> bool:
        if usage_id in self.consumed:
            return False
        reserved = self.reserved.get(reservation_id)
        if reserved is None or amount > reserved or amount <= 0:
            raise ValueError("invalid usage")
        self.consumed[usage_id] = amount
        self.balance -= amount
        remainder = reserved - amount
        if remainder:
            self.reserved[reservation_id] = remainder
        else:
            self.reserved.pop(reservation_id)
        return True


@dataclass
class PaymentOrder:
    order_id: str
    state: str = "PENDING"
    credited: Decimal = Decimal("0")
    processed_events: set[str] = field(default_factory=set)

    def apply_webhook(self, event_id: str, event_type: str, amount: Decimal) -> bool:
        if event_id in self.processed_events:
            return False
        self.processed_events.add(event_id)
        if event_type == "PAYMENT_CONFIRMED":
            if self.state != "PAID":
                self.state = "PAID"
                self.credited += amount
        elif event_type in {"PAYMENT_PENDING", "PAYMENT_CREATED"}:
            if self.state != "PAID":
                self.state = "PENDING"
        elif event_type == "PAYMENT_FAILED":
            if self.state != "PAID":
                self.state = "FAILED"
        return True


@dataclass
class DebugSession:
    fencing_token: int
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)

    def checkpoint(self, checkpoint_id: str, state: dict[str, Any], token: int) -> str:
        if token != self.fencing_token:
            raise StaleFenceError("stale fencing token")
        canonical = repr(sorted(state.items())).encode()
        digest = sha256(canonical).hexdigest()
        self.checkpoints[checkpoint_id] = {"state": dict(state), "digest": digest}
        return digest

    def replay(self, checkpoint_id: str, token: int) -> dict[str, Any]:
        if token != self.fencing_token:
            raise StaleFenceError("stale fencing token")
        return dict(self.checkpoints[checkpoint_id]["state"])
