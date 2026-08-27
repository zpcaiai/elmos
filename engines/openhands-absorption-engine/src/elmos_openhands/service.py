"""Application-facing control-plane facade over the durable runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ledger import EventLedger
from .models import ExecutionManifest, Identity
from .plane import EventStream
from .runtime import AgentRuntime, RuntimeTurnInput, RuntimeTurnResult


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    status: str
    ledger: str
    external_execution: str
    certification: str


class RuntimeControlPlane:
    """Stable service boundary suitable for HTTP/gRPC/WebSocket adapters.

    Authentication and tenant binding belong to the deployment adapter. This
    facade still requires the caller to pass the authenticated identity and
    checks every read/write against that identity in the ledger.
    """

    def __init__(self, ledger: EventLedger, runtime: AgentRuntime) -> None:
        self.ledger = ledger
        self.runtime = runtime
        self.events = EventStream(ledger)

    def create_run(self, identity: Identity, manifest: ExecutionManifest) -> None:
        self.runtime.register(identity, manifest)

    def turn(self, request: RuntimeTurnInput) -> RuntimeTurnResult:
        return self.runtime.run_turn(request)

    def resume(self, identity: Identity, manifest: ExecutionManifest) -> dict[str, Any]:
        return self.runtime.resume(identity, manifest)

    def cancel(self, identity: Identity, reason: str) -> None:
        self.runtime.cancel(identity, reason)

    def event_page(self, identity: Identity, *, after_seq: int = -1, limit: int = 100) -> tuple[Any, ...]:
        return self.events.read(identity, after_seq=after_seq, limit=limit)

    def health(self) -> ServiceHealth:
        return ServiceHealth("ok", "configured", "adapter-bound", "NOT_CERTIFIED")
