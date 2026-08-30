"""Rebuildable runtime, timeline, cost, verification and context projections."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import ContractViolation, CorruptState
from .models import Event, Identity, canonical_json, digest_of

Reducer = Callable[[Mapping[str, Any], Event], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ProjectionDefinition:
    name: str
    initial: Mapping[str, Any]
    reducer: Reducer

    def __post_init__(self) -> None:
        if not self.name:
            raise ContractViolation("projection name is required")


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    tenant_id: str
    run_id: str
    name: str
    event_seq: int
    head_digest: str
    body: Mapping[str, Any]
    checksum: str


class ProjectionLedger(Protocol):
    def assert_identity(self, identity: Identity) -> Any: ...
    def events(self, tenant_id: str, run_id: str, *, after_seq: int = -1, limit: int = 1000) -> list[Event]: ...


class ProjectionStore:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS materialized_projections(tenant_id TEXT NOT NULL,run_id TEXT NOT NULL,name TEXT NOT NULL,event_seq INTEGER NOT NULL,head_digest TEXT NOT NULL,body_json TEXT NOT NULL,checksum TEXT NOT NULL,PRIMARY KEY(tenant_id,run_id,name));
               CREATE TABLE IF NOT EXISTS projection_pending(tenant_id TEXT NOT NULL,run_id TEXT NOT NULL,seq INTEGER NOT NULL,event_json TEXT NOT NULL,event_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,run_id,seq));"""
        )

    def close(self) -> None:
        self._connection.close()

    def put(self, snapshot: ProjectionSnapshot) -> None:
        self._connection.execute("INSERT INTO materialized_projections VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id,run_id,name) DO UPDATE SET event_seq=excluded.event_seq,head_digest=excluded.head_digest,body_json=excluded.body_json,checksum=excluded.checksum", (snapshot.tenant_id, snapshot.run_id, snapshot.name, snapshot.event_seq, snapshot.head_digest, canonical_json(dict(snapshot.body)), snapshot.checksum))

    def get(self, tenant_id: str, run_id: str, name: str) -> ProjectionSnapshot | None:
        row = self._connection.execute("SELECT * FROM materialized_projections WHERE tenant_id=? AND run_id=? AND name=?", (tenant_id, run_id, name)).fetchone()
        if row is None:
            return None
        return ProjectionSnapshot(tenant_id, run_id, name, int(row["event_seq"]), row["head_digest"], json.loads(row["body_json"]), row["checksum"])

    def queue(self, event: Event) -> None:
        encoded = canonical_json(event.as_dict())
        row = self._connection.execute("SELECT event_digest FROM projection_pending WHERE tenant_id=? AND run_id=? AND seq=?", (event.tenant_id, event.run_id, event.seq)).fetchone()
        if row is not None and row["event_digest"] != event.digest:
            raise CorruptState("projection consumer received conflicting event sequence")
        self._connection.execute("INSERT OR IGNORE INTO projection_pending VALUES(?,?,?,?,?)", (event.tenant_id, event.run_id, event.seq, encoded, event.digest))

    def pending(self, tenant_id: str, run_id: str, after_seq: int) -> tuple[Event, ...]:
        rows = self._connection.execute("SELECT event_json FROM projection_pending WHERE tenant_id=? AND run_id=? AND seq>? ORDER BY seq", (tenant_id, run_id, after_seq)).fetchall()
        return tuple(_event(json.loads(row["event_json"])) for row in rows)


class ProjectionEngine:
    def __init__(self, ledger: ProjectionLedger, store: ProjectionStore, definitions: Iterable[ProjectionDefinition] | None = None) -> None:
        values = tuple(definitions or builtin_projections())
        self.ledger, self.store = ledger, store
        self.definitions = {definition.name: definition for definition in values}
        if len(self.definitions) != len(values):
            raise ContractViolation("projection names must be unique")

    def rebuild(self, identity: Identity) -> Mapping[str, ProjectionSnapshot]:
        self.ledger.assert_identity(identity)
        events = tuple(self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000))
        _verify_order(events)
        result: dict[str, ProjectionSnapshot] = {}
        for definition in self.definitions.values():
            body: Mapping[str, Any] = json.loads(canonical_json(definition.initial))
            for event in events:
                body = definition.reducer(body, event)
            sequence = -1 if not events else events[-1].seq
            head = "genesis" if not events else str(events[-1].digest)
            checksum = digest_of({"name": definition.name, "event_seq": sequence, "head": head, "body": body})
            snapshot = ProjectionSnapshot(identity.tenant_id, identity.run_id, definition.name, sequence, head, body, checksum)
            self.store.put(snapshot)
            result[definition.name] = snapshot
        return result

    def consume(self, event: Event) -> Mapping[str, ProjectionSnapshot]:
        self.store.queue(event)
        result: dict[str, ProjectionSnapshot] = {}
        for definition in self.definitions.values():
            current = self.store.get(event.tenant_id, event.run_id, definition.name)
            sequence = -1 if current is None else current.event_seq
            head = "genesis" if current is None else current.head_digest
            body = json.loads(canonical_json(definition.initial if current is None else current.body))
            pending = self.store.pending(event.tenant_id, event.run_id, sequence)
            for item in pending:
                if item.seq != sequence + 1:
                    break
                body = definition.reducer(body, item)
                sequence = item.seq
                head = str(item.digest)
            snapshot = ProjectionSnapshot(event.tenant_id, event.run_id, definition.name, sequence, head, body, digest_of({"name": definition.name, "event_seq": sequence, "head": head, "body": body}))
            self.store.put(snapshot)
            result[definition.name] = snapshot
        return result

    def compare_rebuild(self, identity: Identity) -> Mapping[str, bool]:
        before = {name: self.store.get(identity.tenant_id, identity.run_id, name) for name in self.definitions}
        rebuilt = self.rebuild(identity)
        result: dict[str, bool] = {}
        for name in self.definitions:
            prior = before[name]
            result[name] = prior is not None and prior.checksum == rebuilt[name].checksum
        return result


def builtin_projections() -> tuple[ProjectionDefinition, ...]:
    return (
        ProjectionDefinition("runtime", {"status": "queued", "actions": {}, "last_event_seq": -1}, _runtime),
        ProjectionDefinition("timeline", {"items": []}, _timeline),
        ProjectionDefinition("cost", {"input_tokens": 0, "output_tokens": 0, "cost_micros": 0, "by_provider": {}}, _cost),
        ProjectionDefinition("verification", {"status": "not_run", "checks": {}, "evidence_refs": []}, _verification),
        ProjectionDefinition("context_candidates", {"candidates": {}, "fingerprints": []}, _context),
    )


def _runtime(state: Mapping[str, Any], event: Event) -> Mapping[str, Any]:
    value = {**state, "actions": dict(state.get("actions", {})), "last_event_seq": event.seq, "head_digest": event.digest}
    if event.event_type == "run.status":
        value["status"] = event.payload.get("status", value["status"])
    elif event.event_type == "tool.observed":
        value["actions"][str(event.payload.get("action_id", ""))] = dict(event.payload)
    return value


def _timeline(state: Mapping[str, Any], event: Event) -> Mapping[str, Any]:
    items = list(state.get("items", []))
    items.append({"seq": event.seq, "type": event.event_type, "timestamp": event.timestamp, "node_id": event.node_id, "digest": event.digest})
    return {"items": items}


def _cost(state: Mapping[str, Any], event: Event) -> Mapping[str, Any]:
    value = {**state, "by_provider": dict(state.get("by_provider", {}))}
    if event.usage is None:
        return value
    value["input_tokens"] = int(value["input_tokens"]) + event.usage.input_tokens
    value["output_tokens"] = int(value["output_tokens"]) + event.usage.output_tokens
    value["cost_micros"] = int(value["cost_micros"]) + event.usage.cost_micros
    provider = str(event.payload.get("provider", "unknown"))
    value["by_provider"][provider] = int(value["by_provider"].get(provider, 0)) + event.usage.cost_micros
    return value


def _verification(state: Mapping[str, Any], event: Event) -> Mapping[str, Any]:
    value = {**state, "checks": dict(state.get("checks", {})), "evidence_refs": list(state.get("evidence_refs", []))}
    if event.event_type == "verification.completed":
        value["status"] = event.payload.get("status", "blocked")
        for check in event.payload.get("checks", []):
            value["checks"][str(check.get("name"))] = dict(check)
            value["evidence_refs"].extend(check.get("evidence_refs", []))
    return value


def _context(state: Mapping[str, Any], event: Event) -> Mapping[str, Any]:
    value = {**state, "candidates": dict(state.get("candidates", {})), "fingerprints": list(state.get("fingerprints", []))}
    if event.event_type == "context.candidate":
        value["candidates"][str(event.payload.get("candidate_id"))] = dict(event.payload)
    elif event.event_type == "context.built":
        value["fingerprints"].append(str(event.payload.get("fingerprint")))
    return value


def _verify_order(events: tuple[Event, ...]) -> None:
    previous: str | None = None
    for expected, event in enumerate(events):
        if event.seq != expected or event.previous_digest != previous or event.digest != event.computed_digest():
            raise CorruptState("projection rebuild input is not a valid event chain")
        previous = event.digest


def _event(value: Mapping[str, Any]) -> Event:
    from .models import ArtifactRef, Usage

    return Event(
        str(value["event_id"]), str(value["tenant_id"]), str(value["run_id"]), int(value["seq"]), str(value["event_type"]), dict(value["payload"]), str(value["timestamp"]),
        value.get("node_id"), value.get("agent_id"), value.get("causation_event_id"), value.get("correlation_id"), value.get("idempotency_key"),
        tuple(ArtifactRef(**item) for item in value.get("artifact_refs", ())), value.get("policy_decision"), None if value.get("usage") is None else Usage(**value["usage"]), value.get("cost"), value.get("previous_digest"), value.get("digest"), str(value.get("schema_version", "1.0")),
    )
