"""Compiled firewall rule DSL, taint tracking and durable approvals."""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ContractViolation, TenantIsolationError
from .firewall import ActionFirewall, FirewallContext, FirewallResult
from .models import Action, Identity, PolicyDecision, RiskLevel, digest_of, new_id


@dataclass(frozen=True, slots=True)
class PolicyRule:
    rule_id: str
    priority: int
    effect: str
    operations: frozenset[str] = frozenset()
    tools: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    risk_at_least: RiskLevel | None = None
    domains: frozenset[str] = frozenset()
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id or self.effect not in {"allow", "deny", "require_approval"} or not self.reason:
            raise ContractViolation("policy rule is invalid")

    def matches(self, action: Action, risk: RiskLevel) -> bool:
        operation = str(action.args.get("operation", ""))
        if self.operations and operation not in self.operations:
            return False
        if self.tools and action.tool not in self.tools:
            return False
        if self.capabilities and not self.capabilities.intersection(action.required_capabilities):
            return False
        if self.risk_at_least is not None and int(risk.value[1:]) < int(self.risk_at_least.value[1:]):
            return False
        if self.domains:
            hosts = set(_hosts(action.args))
            if not hosts or not hosts.issubset(self.domains):
                return False
        return True


class PolicyCompiler:
    """Compiles a bounded data DSL; no expressions or source code execute."""

    ALLOWED_KEYS = frozenset({"id", "priority", "effect", "operations", "tools", "capabilities", "risk_at_least", "domains", "reason"})

    def compile(self, document: Mapping[str, Any]) -> tuple[PolicyRule, ...]:
        if str(document.get("version", "")) == "" or not isinstance(document.get("rules"), list):
            raise ContractViolation("policy document requires version and rules")
        rows: list[PolicyRule] = []
        for raw in document["rules"]:
            if not isinstance(raw, Mapping) or set(raw) - self.ALLOWED_KEYS:
                raise ContractViolation("policy rule contains unsupported fields")
            risk = None if raw.get("risk_at_least") is None else RiskLevel(str(raw["risk_at_least"]))
            rows.append(PolicyRule(str(raw["id"]), int(raw.get("priority", 100)), str(raw["effect"]), frozenset(map(str, raw.get("operations", ()))), frozenset(map(str, raw.get("tools", ()))), frozenset(map(str, raw.get("capabilities", ()))), risk, frozenset(map(str, raw.get("domains", ()))), str(raw["reason"])))
        if len({row.rule_id for row in rows}) != len(rows):
            raise ContractViolation("policy rule identifiers must be unique")
        return tuple(sorted(rows, key=lambda row: (row.priority, row.rule_id)))


@dataclass(frozen=True, slots=True)
class RuleDecision:
    effect: str
    matched_rules: tuple[str, ...]
    reasons: tuple[str, ...]


class CompiledPolicyEngine:
    def __init__(self, rules: Iterable[PolicyRule]) -> None:
        self.rules = tuple(rules)

    def evaluate(self, action: Action, risk: RiskLevel) -> RuleDecision:
        matched = [rule for rule in self.rules if rule.matches(action, risk)]
        if not matched:
            return RuleDecision("allow", (), ("NO_ADDITIONAL_RULE",))
        effects = {rule.effect for rule in matched}
        effect = "deny" if "deny" in effects else "require_approval" if "require_approval" in effects else "allow"
        return RuleDecision(effect, tuple(rule.rule_id for rule in matched), tuple(rule.reason for rule in matched))


class SecretTaintTracker:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str, str, str, str], tuple[str, ...]] = {}
        self._lock = threading.RLock()

    def register(self, identity: Identity, secret_ref: str, value: str) -> None:
        if not secret_ref or not value:
            raise ContractViolation("taint registration requires reference and value")
        variants = {value, urllib.parse.quote(value), base64.b64encode(value.encode()).decode()}
        scope = identity.scope()
        with self._lock:
            self._values[scope] = tuple(sorted(set(self._values.get(scope, ())) | variants))

    def detect(self, identity: Identity, value: Any) -> tuple[str, ...]:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        with self._lock:
            variants = self._values.get(identity.scope(), ())
        return tuple(digest_of(item) for item in variants if item and item in serialized)

    def redact(self, identity: Identity, value: str) -> str:
        with self._lock:
            variants = self._values.get(identity.scope(), ())
        for item in sorted(variants, key=len, reverse=True):
            value = value.replace(item, "[REDACTED]")
        return value


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    identity: Identity
    action_digest: str
    risk_level: RiskLevel
    requester: str
    reason: str
    required_approvals: int
    expires_at: float
    change_window_start: float | None
    change_window_end: float | None
    state: str


class ApprovalWorkflow:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS approvals(approval_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,agent_id TEXT,action_digest TEXT NOT NULL,risk_level TEXT NOT NULL,requester TEXT NOT NULL,reason TEXT NOT NULL,required_approvals INTEGER NOT NULL,expires_at REAL NOT NULL,change_window_start REAL,change_window_end REAL,state TEXT NOT NULL);
               CREATE TABLE IF NOT EXISTS approval_decisions(approval_id TEXT NOT NULL,actor TEXT NOT NULL,decision TEXT NOT NULL,reason TEXT NOT NULL,decided_at REAL NOT NULL,PRIMARY KEY(approval_id,actor));"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        self._connection.close()

    def request(self, identity: Identity, action: Action, risk: RiskLevel, *, requester: str, reason: str, ttl_seconds: float = 900.0, change_window: tuple[float, float] | None = None) -> ApprovalRequest:
        if risk not in {RiskLevel.R4, RiskLevel.R5, RiskLevel.R6} or not requester or not reason or ttl_seconds <= 0 or ttl_seconds > 86_400:
            raise ContractViolation("approval request is invalid")
        required = 2 if risk == RiskLevel.R6 else 1
        if risk == RiskLevel.R6 and change_window is None:
            raise ContractViolation("R6 approval requires an explicit change window")
        if change_window is not None and change_window[1] <= change_window[0]:
            raise ContractViolation("approval change window is invalid")
        action_digest = digest_of(action.as_dict())
        approval_id = "approval_" + digest_of({"identity": identity.scope(), "action": action_digest, "requester": requester, "reason": reason}).split(":", 1)[1]
        now = time.time()
        with self._lock:
            self._connection.execute("INSERT OR IGNORE INTO approvals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending')", (approval_id, *identity.scope(), identity.agent_id, action_digest, risk.value, requester, reason, required, now + ttl_seconds, None if change_window is None else change_window[0], None if change_window is None else change_window[1]))
        return self.get(identity, approval_id)

    def decide(self, identity: Identity, approval_id: str, *, actor: str, decision: str, reason: str, now: float | None = None) -> ApprovalRequest:
        now = time.time() if now is None else now
        request = self.get(identity, approval_id)
        if request.state != "pending" or request.expires_at <= now or actor == request.requester or decision not in {"approve", "deny"} or not reason:
            raise ContractViolation("approval decision is invalid, expired, terminal or self-approved")
        with self._lock:
            self._connection.execute("INSERT INTO approval_decisions VALUES(?,?,?,?,?)", (approval_id, actor, decision, reason, now))
            approvals = int(self._connection.execute("SELECT COUNT(*) FROM approval_decisions WHERE approval_id=? AND decision='approve'", (approval_id,)).fetchone()[0])
            denials = int(self._connection.execute("SELECT COUNT(*) FROM approval_decisions WHERE approval_id=? AND decision='deny'", (approval_id,)).fetchone()[0])
            state = "denied" if denials else "approved" if approvals >= request.required_approvals else "pending"
            self._connection.execute("UPDATE approvals SET state=? WHERE approval_id=?", (state, approval_id))
        return self.get(identity, approval_id)

    def validate(self, identity: Identity, approval_id: str, action: Action, risk: RiskLevel, *, now: float | None = None) -> tuple[str, ...]:
        now = time.time() if now is None else now
        request = self.get(identity, approval_id)
        if request.state != "approved" or request.expires_at <= now or request.action_digest != digest_of(action.as_dict()) or request.risk_level != risk:
            raise ContractViolation("approval is absent, expired or not scoped to this action")
        if request.change_window_start is not None and not (request.change_window_start <= now <= (request.change_window_end or request.change_window_start)):
            raise ContractViolation("approval is outside its change window")
        rows = self._connection.execute("SELECT actor FROM approval_decisions WHERE approval_id=? AND decision='approve' ORDER BY actor", (approval_id,)).fetchall()
        return tuple(row["actor"] for row in rows)

    def get(self, identity: Identity, approval_id: str) -> ApprovalRequest:
        row = self._connection.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        if (row["tenant_id"], row["project_id"], row["task_id"], row["run_id"], row["node_id"]) != identity.scope():
            raise TenantIsolationError("approval belongs to another scope")
        return ApprovalRequest(approval_id, identity, row["action_digest"], RiskLevel(row["risk_level"]), row["requester"], row["reason"], int(row["required_approvals"]), float(row["expires_at"]), row["change_window_start"], row["change_window_end"], row["state"])


class DurableKillSwitch:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("CREATE TABLE IF NOT EXISTS kill_switches(scope_type TEXT NOT NULL,scope_id TEXT NOT NULL,state TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,version INTEGER NOT NULL,PRIMARY KEY(scope_type,scope_id))")

    def close(self) -> None:
        self._connection.close()

    def set(self, scope_type: str, scope_id: str, *, active: bool, actor: str, reason: str) -> None:
        if scope_type not in {"global", "tenant", "package", "tool"} or not scope_id or not actor or not reason:
            raise ContractViolation("kill-switch mutation is invalid")
        self._connection.execute("INSERT INTO kill_switches VALUES(?,?,?,?,?,1) ON CONFLICT(scope_type,scope_id) DO UPDATE SET state=excluded.state,actor=excluded.actor,reason=excluded.reason,version=kill_switches.version+1", (scope_type, scope_id, "active" if active else "inactive", actor, reason))

    def active(self, identity: Identity, *, package_name: str | None, tool: str) -> tuple[str, ...]:
        scopes = (("global", "global"), ("tenant", identity.tenant_id), ("tool", tool), ("package", package_name or ""))
        active: list[str] = []
        for scope_type, scope_id in scopes:
            if not scope_id:
                continue
            row = self._connection.execute("SELECT state FROM kill_switches WHERE scope_type=? AND scope_id=?", (scope_type, scope_id)).fetchone()
            if row is not None and row["state"] == "active":
                active.append(f"{scope_type}:{scope_id}")
        return tuple(active)


class GovernedActionFirewall:
    """Composes deterministic guards, DSL, taint, approvals and kill switches."""

    def __init__(self, base: ActionFirewall, policy: CompiledPolicyEngine, approvals: ApprovalWorkflow, taints: SecretTaintTracker, kill_switches: DurableKillSwitch) -> None:
        self.base, self.policy, self.approvals, self.taints, self.kill_switches = base, policy, approvals, taints, kill_switches

    def decide(self, action: Action, context: FirewallContext, *, approved_by: str | None = None) -> FirewallResult:
        risk = action.risk_hint or self.base.classify(action)
        active = self.kill_switches.active(context.identity, package_name=context.package_name, tool=action.tool)
        if active:
            return self._result("deny", risk, ("durable_kill_switch",), ("KILL_SWITCH_ACTIVE:" + ",".join(active),), context, None, action.args)
        taints = self.taints.detect(context.identity, action.args)
        if taints:
            return self._result("deny", risk, ("secret_taint_check",), ("SECRET_TAINT_DETECTED:" + ",".join(taints),), context, None, action.args)
        base = self.base.decide(action, context)
        if base.decision.decision == "deny":
            return base
        rule = self.policy.evaluate(action, risk)
        if rule.effect == "deny":
            return self._result("deny", risk, rule.matched_rules, rule.reasons, context, None, base.normalized_args)
        approval_needed = base.decision.decision == "require_approval" or rule.effect == "require_approval"
        if approval_needed:
            if not approved_by:
                return self._result("require_approval", risk, (*base.decision.rules, *rule.matched_rules), (*base.decision.reasons, *rule.reasons), context, None, base.normalized_args)
            approvers = self.approvals.validate(context.identity, approved_by, action, risk)
            return self._result("allow", risk, (*base.decision.rules, *rule.matched_rules, "durable_approval"), ("APPROVED_BY:" + ",".join(approvers),), context, ",".join(approvers), base.normalized_args)
        return self._result("allow", risk, (*base.decision.rules, *rule.matched_rules), (*base.decision.reasons, *rule.reasons), context, None, base.normalized_args)

    @staticmethod
    def _result(decision: str, risk: RiskLevel, rules: Iterable[str], reasons: Iterable[str], context: FirewallContext, approved_by: str | None, normalized: Mapping[str, Any]) -> FirewallResult:
        value = PolicyDecision(new_id(), decision, risk, tuple(dict.fromkeys(rules)), tuple(dict.fromkeys(reasons)), context.policy_version, approved_by)
        return FirewallResult(value, json.loads(json.dumps(dict(normalized), default=str)))


def _hosts(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _hosts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _hosts(item)
    elif isinstance(value, str):
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            yield parsed.hostname.lower()
