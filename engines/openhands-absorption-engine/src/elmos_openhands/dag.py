"""Durable fan-out/fan-in multi-agent DAG."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from typing import Iterable

from .errors import ContractViolation, LeaseLost, TenantIsolationError
from .ledger import EventLedger
from .models import Identity, new_id


@dataclass(frozen=True, slots=True)
class AgentNode:
    node_id: str
    run_id: str
    tenant_id: str
    depends_on: tuple[str, ...]
    status: str
    budget_micros: int
    owner: str | None = None
    fencing_token: str | None = None
    attempt: int = 0
    result_ref: str | None = None


class DurableAgentDag:
    def __init__(self, database: str = ":memory:", *, ledger: EventLedger | None = None) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("""CREATE TABLE IF NOT EXISTS agent_nodes(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,scope_node_id TEXT NOT NULL,node_id TEXT NOT NULL,depends_on TEXT NOT NULL,status TEXT NOT NULL,budget_micros INTEGER NOT NULL,owner TEXT,fencing_token TEXT,attempt INTEGER NOT NULL,result_ref TEXT,version INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,run_id,scope_node_id,node_id))""")
        self._lock = threading.RLock()
        self.ledger = ledger

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def add(self, identity: Identity, node_id: str, depends_on: Iterable[str] = (), *, budget_micros: int = 0) -> AgentNode:
        dependencies = tuple(dict.fromkeys(depends_on))
        if node_id in dependencies or budget_micros < 0:
            raise ContractViolation("DAG node has invalid dependency or budget")
        with self._lock:
            self._assert_run_scope(identity)
            existing = self._connection.execute(
                "SELECT * FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?",
                (*identity.scope(), node_id),
            ).fetchone()
            if existing is not None:
                existing_dependencies = tuple(item for item in existing["depends_on"].split(",") if item)
                if existing_dependencies == dependencies and int(existing["budget_micros"]) == budget_micros:
                    return self._node(existing)
                raise ContractViolation("DAG node already exists with another contract")
            all_nodes = {row["node_id"] for row in self._connection.execute("SELECT node_id FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=?", identity.scope())}
            if any(dependency not in all_nodes for dependency in dependencies):
                raise ContractViolation("DAG dependency must already exist")
            try:
                self._connection.execute("INSERT INTO agent_nodes(tenant_id,project_id,task_id,run_id,scope_node_id,node_id,depends_on,status,budget_micros,attempt) VALUES(?,?,?,?,?,?,?,?,?,0)", (*identity.scope(), node_id, ",".join(dependencies), "ready" if not dependencies else "waiting", budget_micros))
            except sqlite3.IntegrityError as error:
                self._assert_run_scope(identity)
                raise ContractViolation("DAG node already exists") from error
        return self.get(identity, node_id)

    def ready(self, identity: Identity) -> tuple[AgentNode, ...]:
        self._assert_run_scope(identity)
        rows = self._connection.execute("SELECT * FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? ORDER BY node_id", identity.scope()).fetchall()
        result: list[AgentNode] = []
        for row in rows:
            if row["status"] != "waiting":
                if row["status"] == "ready":
                    result.append(self._node(row))
                continue
            dependencies = [item for item in row["depends_on"].split(",") if item]
            statuses = {dependency: self._connection.execute("SELECT status FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?", (*identity.scope(), dependency)).fetchone()[0] for dependency in dependencies}
            if all(status == "succeeded" for status in statuses.values()):
                self._connection.execute("UPDATE agent_nodes SET status='ready',version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND status='waiting'", (*identity.scope(), row["node_id"]))
                result.append(self.get(identity, row["node_id"]))
        return tuple(result)

    def claim(self, identity: Identity, node_id: str, owner: str) -> AgentNode:
        node = self.get(identity, node_id)
        if node.status == "running" and node.owner == owner and node.fencing_token:
            return node
        if node.status != "ready":
            raise LeaseLost("node is not ready")
        token = new_id()
        updated = self._connection.execute("UPDATE agent_nodes SET status='running',owner=?,fencing_token=?,attempt=attempt+1,version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND status='ready'", (owner, token, *identity.scope(), node_id)).rowcount
        if updated != 1:
            raise LeaseLost("node claim lost a concurrent race")
        return self.get(identity, node_id)

    def complete(self, identity: Identity, node_id: str, owner: str, fencing_token: str, result_ref: str) -> AgentNode:
        if not result_ref:
            raise ContractViolation("node result must reference an artifact")
        node = self.get(identity, node_id)
        if node.status == "succeeded" and node.owner == owner and node.fencing_token == fencing_token and node.result_ref == result_ref:
            return node
        updated = self._connection.execute("UPDATE agent_nodes SET status='succeeded',result_ref=?,version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND owner=? AND fencing_token=? AND status='running'", (result_ref, *identity.scope(), node_id, owner, fencing_token)).rowcount
        if updated != 1:
            raise LeaseLost("node completion rejected by fencing")
        return self.get(identity, node_id)

    def fail(self, identity: Identity, node_id: str, owner: str, fencing_token: str, result_ref: str | None = None) -> AgentNode:
        node = self.get(identity, node_id)
        if node.status == "failed" and node.owner == owner and node.fencing_token == fencing_token and node.result_ref == result_ref:
            return node
        updated = self._connection.execute("UPDATE agent_nodes SET status='failed',result_ref=?,version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND owner=? AND fencing_token=? AND status='running'", (result_ref, *identity.scope(), node_id, owner, fencing_token)).rowcount
        if updated != 1:
            raise LeaseLost("node failure rejected by fencing")
        return self.get(identity, node_id)

    def cancel(self, identity: Identity, node_id: str, reason: str) -> AgentNode:
        if not reason:
            raise ContractViolation("cancellation reason is required")
        self._connection.execute("UPDATE agent_nodes SET status='cancelled',version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND status IN ('waiting','ready','running')", (*identity.scope(), node_id))
        return self.get(identity, node_id)

    def remove(self, identity: Identity, node_id: str, reason: str) -> None:
        """Remove an unstarted leaf during a versioned plan amendment."""
        if not reason:
            raise ContractViolation("DAG removal reason is required")
        try:
            node = self.get(identity, node_id)
        except KeyError:
            return
        if node.status not in {"waiting", "ready", "cancelled"}:
            raise ContractViolation("only unstarted or cancelled DAG nodes may be removed")
        dependent = self._connection.execute(
            "SELECT 1 FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id<>? AND (',' || depends_on || ',') LIKE ? LIMIT 1",
            (*identity.scope(), node_id, "%," + node_id + ",%"),
        ).fetchone()
        if dependent is not None:
            raise ContractViolation("DAG node cannot be removed while dependents reference it")
        self._connection.execute("DELETE FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND status IN ('waiting','ready','cancelled')", (*identity.scope(), node_id))

    def amend(self, identity: Identity, node_id: str, *, depends_on: Iterable[str]) -> AgentNode:
        node = self.get(identity, node_id)
        if node.status not in {"waiting", "ready"}:
            raise ContractViolation("only unstarted DAG nodes may be amended")
        dependencies = tuple(dict.fromkeys(depends_on))
        if node_id in dependencies:
            raise ContractViolation("DAG cannot depend on itself")
        existing = {row["node_id"]: tuple(item for item in row["depends_on"].split(",") if item) for row in self._connection.execute("SELECT node_id,depends_on FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=?", identity.scope())}
        if any(dependency not in existing for dependency in dependencies):
            raise ContractViolation("DAG dependency must already exist")
        if existing.get(node_id) == dependencies:
            return node
        existing[node_id] = dependencies
        if _has_cycle(existing):
            raise ContractViolation("DAG amendment introduces a cycle")
        self._connection.execute("UPDATE agent_nodes SET depends_on=?,status=?,version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?", (",".join(dependencies), "ready" if not dependencies else "waiting", *identity.scope(), node_id))
        return self.get(identity, node_id)

    def get(self, identity: Identity, node_id: str) -> AgentNode:
        row = self._connection.execute("SELECT * FROM agent_nodes WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?", (*identity.scope(), node_id)).fetchone()
        if row is None:
            self._assert_run_scope(identity)
            raise KeyError(node_id)
        return self._node(row)

    def _assert_run_scope(self, identity: Identity) -> None:
        row = self._connection.execute(
            "SELECT project_id,task_id FROM agent_nodes WHERE tenant_id=? AND run_id=? AND scope_node_id=? LIMIT 1",
            (identity.tenant_id, identity.run_id, identity.node_id),
        ).fetchone()
        if row is not None and (row["project_id"], row["task_id"]) != (identity.project_id, identity.task_id):
            raise TenantIsolationError("DAG run is bound to another project/task")

    @staticmethod
    def _node(row: sqlite3.Row) -> AgentNode:
        return AgentNode(row["node_id"], row["run_id"], row["tenant_id"], tuple(item for item in row["depends_on"].split(",") if item), row["status"], row["budget_micros"], row["owner"], row["fencing_token"], row["attempt"], row["result_ref"])


def _has_cycle(graph: dict[str, tuple[str, ...]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
