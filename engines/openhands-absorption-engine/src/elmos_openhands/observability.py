"""Minimal OTel-shaped telemetry and exact micro-unit cost metering."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from .errors import ContractViolation
from .ledger import EventLedger
from .models import Identity, Usage


@dataclass(frozen=True, slots=True)
class Span:
    name: str
    attributes: Mapping[str, str]
    started_at: float
    ended_at: float
    status: str


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._lock = threading.RLock()

    def increment(self, name: str, value: int = 1, *, attributes: Mapping[str, str] | None = None) -> None:
        if value < 0:
            raise ContractViolation("metrics cannot decrement through increment")
        key = name + ("{" + ",".join(f"{k}={v}" for k, v in sorted((attributes or {}).items())) + "}" if attributes else "")
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, str]) -> Iterator[dict[str, Any]]:
        started = time.monotonic()
        payload: dict[str, Any] = {"name": name, "attributes": dict(attributes)}
        try:
            yield payload
        except Exception:
            payload["status"] = "error"
            raise
        else:
            payload["status"] = "ok"
        finally:
            payload["duration_ms"] = int((time.monotonic() - started) * 1000)


class CostMeter:
    """Records exact integer micro-costs and reconciles them to an invoice sample."""

    def __init__(self, ledger: EventLedger) -> None:
        self.ledger = ledger

    def record(self, identity: Identity, *, usage: Usage, unit: str, source: str) -> None:
        if not unit or not source:
            raise ContractViolation("cost unit and source are required")
        self.ledger.append(identity, "cost.usage", {"unit": unit, "source": source, "cost_micros": usage.cost_micros, "usage": usage.as_dict()}, idempotency_key=f"cost:{source}:{unit}:{usage.cost_micros}", usage=usage, cost={"unit": unit, "source": source, "cost_micros": usage.cost_micros})

    def reconcile(self, identity: Identity, invoice_micros: int) -> dict[str, int | str]:
        if invoice_micros < 0:
            raise ContractViolation("invoice amount cannot be negative")
        observed = sum(event.usage.cost_micros for event in self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000) if event.usage is not None)
        variance = observed - invoice_micros
        status = "pass" if invoice_micros == 0 and observed == 0 or invoice_micros != 0 and abs(variance) * 100 <= invoice_micros else "incident"
        return {"observed_micros": observed, "invoice_micros": invoice_micros, "variance_micros": variance, "status": status}
