"""Minimal OTel-shaped telemetry and exact micro-unit cost metering."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        self.ledger.assert_identity(identity)
        observed = sum(event.usage.cost_micros for event in self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000) if event.usage is not None)
        variance = observed - invoice_micros
        status = "pass" if invoice_micros == 0 and observed == 0 or invoice_micros != 0 and abs(variance) * 100 <= invoice_micros else "incident"
        return {"observed_micros": observed, "invoice_micros": invoice_micros, "variance_micros": variance, "status": status}


@dataclass(frozen=True, slots=True)
class UsageAttribution:
    identity: Identity
    provider: str
    model: str
    tool: str | None = None
    region: str = "local"

    def attributes(self) -> dict[str, str]:
        return {
            "elmos.tenant.id": self.identity.tenant_id, "elmos.project.id": self.identity.project_id,
            "elmos.task.id": self.identity.task_id, "elmos.run.id": self.identity.run_id,
            "elmos.node.id": self.identity.node_id, "gen_ai.system": self.provider,
            "gen_ai.request.model": self.model, "elmos.tool.name": self.tool or "none", "cloud.region": self.region,
        }


class OpenTelemetryAdapter:
    """Real OTel bridge; exporter/provider configuration remains deployment-owned."""

    def __init__(self, *, service_name: str = "elmos-openhands") -> None:
        try:
            from opentelemetry import metrics, trace
        except ImportError as error:  # pragma: no cover - optional production dependency
            from .errors import NotConfigured

            raise NotConfigured("opentelemetry-api is required for production telemetry") from error
        self.tracer = trace.get_tracer(service_name)
        self.meter = metrics.get_meter(service_name)
        self.turns = self.meter.create_counter("elmos.agent.turns")
        self.tool_calls = self.meter.create_counter("elmos.tool.calls")
        self.tokens = self.meter.create_counter("gen_ai.client.token.usage")
        self.cost = self.meter.create_counter("elmos.cost.micros")

    @contextmanager
    def span(self, name: str, attribution: UsageAttribution, attributes: Mapping[str, str] | None = None) -> Iterator[Any]:
        values = {**attribution.attributes(), **dict(attributes or {})}
        with self.tracer.start_as_current_span(name, attributes=values) as span:
            yield span

    def record_usage(self, attribution: UsageAttribution, usage: Usage) -> None:
        attributes = attribution.attributes()
        self.tokens.add(usage.input_tokens, {**attributes, "gen_ai.token.type": "input"})
        self.tokens.add(usage.output_tokens, {**attributes, "gen_ai.token.type": "output"})
        self.cost.add(usage.cost_micros, attributes)


@dataclass(frozen=True, slots=True)
class FinOpsBudget:
    max_cost_micros: int
    max_tokens: int
    max_cpu_micros: int
    max_storage_byte_seconds: int

    def __post_init__(self) -> None:
        if min(self.max_cost_micros, self.max_tokens, self.max_cpu_micros, self.max_storage_byte_seconds) < 0:
            raise ContractViolation("FinOps budget cannot be negative")


class FinOpsLedger:
    """Exact integer usage attribution, alerts and invoice reconciliation."""

    def __init__(self, database: str | Path = ":memory:", *, alert: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS finops_budgets(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,budget_json TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id));
               CREATE TABLE IF NOT EXISTS finops_usage(usage_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,tool TEXT,region TEXT NOT NULL,input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,cost_micros INTEGER NOT NULL,cpu_micros INTEGER NOT NULL,storage_byte_seconds INTEGER NOT NULL,source TEXT NOT NULL,invoice_line_id TEXT,created_at REAL NOT NULL);
               CREATE UNIQUE INDEX IF NOT EXISTS finops_invoice_line_unique ON finops_usage(tenant_id,provider,invoice_line_id) WHERE invoice_line_id IS NOT NULL;"""
        )
        self.alert = alert

    def close(self) -> None:
        self._connection.close()

    def set_budget(self, tenant_id: str, project_id: str, budget: FinOpsBudget) -> None:
        import json

        self._connection.execute("INSERT INTO finops_budgets VALUES(?,?,?) ON CONFLICT(tenant_id,project_id) DO UPDATE SET budget_json=excluded.budget_json", (tenant_id, project_id, json.dumps({"max_cost_micros": budget.max_cost_micros, "max_tokens": budget.max_tokens, "max_cpu_micros": budget.max_cpu_micros, "max_storage_byte_seconds": budget.max_storage_byte_seconds}, sort_keys=True)))

    def record(self, attribution: UsageAttribution, usage: Usage, *, cpu_micros: int = 0, storage_byte_seconds: int = 0, source: str, usage_id: str, invoice_line_id: str | None = None) -> Mapping[str, int | bool]:
        if min(cpu_micros, storage_byte_seconds) < 0 or not source or not usage_id:
            raise ContractViolation("FinOps usage record is invalid")
        identity = attribution.identity
        try:
            self._connection.execute("INSERT INTO finops_usage VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (usage_id, *identity.scope(), attribution.provider, attribution.model, attribution.tool, attribution.region, usage.input_tokens, usage.output_tokens, usage.cost_micros, cpu_micros, storage_byte_seconds, source, invoice_line_id, time.time()))
        except sqlite3.IntegrityError:
            row = self._connection.execute("SELECT * FROM finops_usage WHERE usage_id=?", (usage_id,)).fetchone()
            if row is None or int(row["cost_micros"]) != usage.cost_micros:
                raise ContractViolation("FinOps idempotency/invoice line conflict")
        totals = self.totals(identity.tenant_id, identity.project_id)
        budget = self._budget(identity.tenant_id, identity.project_id)
        exceeded = bool(budget and (totals["cost_micros"] > budget.max_cost_micros or totals["tokens"] > budget.max_tokens or totals["cpu_micros"] > budget.max_cpu_micros or totals["storage_byte_seconds"] > budget.max_storage_byte_seconds))
        if exceeded and self.alert is not None:
            self.alert({"kind": "finops_budget_exceeded", "tenant_id": identity.tenant_id, "project_id": identity.project_id, "totals": totals})
        return {**totals, "exceeded": exceeded}

    def enforce(self, tenant_id: str, project_id: str) -> None:
        from .errors import BudgetExceeded

        budget = self._budget(tenant_id, project_id)
        if budget is None:
            raise BudgetExceeded("FinOps budget is not configured")
        totals = self.totals(tenant_id, project_id)
        if totals["cost_micros"] >= budget.max_cost_micros or totals["tokens"] >= budget.max_tokens or totals["cpu_micros"] >= budget.max_cpu_micros or totals["storage_byte_seconds"] >= budget.max_storage_byte_seconds:
            raise BudgetExceeded("FinOps hard stop reached")

    def totals(self, tenant_id: str, project_id: str) -> dict[str, int]:
        row = self._connection.execute("SELECT COALESCE(SUM(input_tokens+output_tokens),0),COALESCE(SUM(cost_micros),0),COALESCE(SUM(cpu_micros),0),COALESCE(SUM(storage_byte_seconds),0) FROM finops_usage WHERE tenant_id=? AND project_id=?", (tenant_id, project_id)).fetchone()
        return {"tokens": int(row[0]), "cost_micros": int(row[1]), "cpu_micros": int(row[2]), "storage_byte_seconds": int(row[3])}

    def reconcile_invoice(self, tenant_id: str, provider: str, invoice_lines: Mapping[str, int]) -> Mapping[str, Any]:
        if any(value < 0 for value in invoice_lines.values()):
            raise ContractViolation("invoice line amounts cannot be negative")
        rows = self._connection.execute("SELECT invoice_line_id,cost_micros FROM finops_usage WHERE tenant_id=? AND provider=? AND invoice_line_id IS NOT NULL", (tenant_id, provider)).fetchall()
        observed = {row["invoice_line_id"]: int(row["cost_micros"]) for row in rows}
        missing = tuple(sorted(set(invoice_lines) - set(observed)))
        extra = tuple(sorted(set(observed) - set(invoice_lines)))
        mismatched = tuple(sorted(line for line in set(invoice_lines) & set(observed) if invoice_lines[line] != observed[line]))
        return {"status": "pass" if not missing and not extra and not mismatched else "incident", "missing": missing, "extra": extra, "mismatched": mismatched, "invoice_micros": sum(invoice_lines.values()), "observed_micros": sum(observed.values())}

    def _budget(self, tenant_id: str, project_id: str) -> FinOpsBudget | None:
        import json

        row = self._connection.execute("SELECT budget_json FROM finops_budgets WHERE tenant_id=? AND project_id=?", (tenant_id, project_id)).fetchone()
        return None if row is None else FinOpsBudget(**json.loads(row["budget_json"]))
