"""Durable, fail-closed runtime for the exact ``agent-step-budget`` Skill.

The runtime records a permit before an Agent step may run and requires that
permit to be settled before another step can be reserved.  It deliberately
does not execute tools or external side effects.  Authorization trust is an
injected adapter so a caller-provided ``ALLOW`` string cannot grant itself
rights.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from .canonical import canonical_bytes, canonical_json, sha256_digest, validate_json_value
from .errors import (
    IdempotencyConflict,
    RequestValidationError,
    StepBudgetAuthorizationDenied,
    StepBudgetConflict,
    StepBudgetExhausted,
    StepBudgetNotFound,
    StepBudgetSchemaMigrationRequired,
    StepBudgetValidationError,
    StepSettlementRequired,
)

SKILL_NAME = "agent-step-budget"
RUNTIME_VERSION = "1.0.0"
REQUEST_SCHEMA_VERSION = "elmos.agent-step-budget.request.v1"
RESPONSE_SCHEMA_VERSION = "elmos.agent-step-budget.response.v1"
STATE_SCHEMA_ID = "elmos.agent-step-budget.store"
STATE_SCHEMA_VERSION = 1
LOCAL_EXECUTED_SELF_ATTESTED = "LOCAL_EXECUTED_SELF_ATTESTED"
NOT_RUN = "NOT_RUN"
NOT_CERTIFIED = "NOT_CERTIFIED"

ACTIVE = "ACTIVE"
EXHAUSTED = "EXHAUSTED"
CANCELLED = "CANCELLED"
BLOCKED_RECONCILIATION = "BLOCKED_RECONCILIATION"

OPERATIONS = frozenset({"admit", "reserve", "settle", "status", "cancel", "audit"})
PERMISSIONS = MappingProxyType(
    {operation: f"agent-step-budget.{operation}" for operation in sorted(OPERATIONS)}
)
COMPLEXITY_MULTIPLIER_BPS = MappingProxyType(
    {"LOW": 7_500, "MEDIUM": 10_000, "HIGH": 15_000, "EXTREME": 20_000}
)
SETTLEMENT_OUTCOMES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"})

_REQUEST_KEYS = {
    "schema_version",
    "operation",
    "skill_name",
    "tenant_id",
    "project_id",
    "run_id",
    "task_id",
    "agent_id",
    "actor_id",
    "idempotency_key",
    "authorization",
    "input",
}
_AUTHORIZATION_KEYS = {
    "authorization_id",
    "decision",
    "permission",
    "subject_actor_id",
    "scope_sha256",
    "issued_at",
    "expires_at",
    "token",
}
_POLICY_KEYS = {
    "base_max_steps",
    "base_max_turns",
    "hard_max_steps",
    "hard_max_turns",
    "complexity",
    "expected_step_cost_microusd",
    "max_cost_microusd",
    "max_tokens",
    "warning_remaining_steps",
    "warning_remaining_turns",
    "reservation_timeout_seconds",
}
_INPUT_KEYS = {
    "admit": {"policy"},
    "reserve": {
        "expected_version",
        "step_id",
        "turn_id",
        "estimated_tokens",
        "estimated_cost_microusd",
        "side_effect",
        "remaining_work",
        "blockers",
    },
    "settle": {
        "expected_version",
        "step_id",
        "outcome",
        "actual_tokens",
        "actual_cost_microusd",
        "failure_type",
        "remaining_work",
        "blockers",
    },
    "status": set(),
    "cancel": {"expected_version", "reason"},
    "audit": {"after_sequence", "limit"},
}
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")
_FAILURE_RE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _normalize_schema_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().removesuffix(";")).strip()


_SCHEMA_TABLE_SQL = {
    "budget_schema": """
        CREATE TABLE budget_schema (
            schema_id TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            schema_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """.strip(),
    "agent_budgets": """
        CREATE TABLE agent_budgets (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            admission_idempotency_key TEXT NOT NULL,
            policy_sha256 TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            max_steps INTEGER NOT NULL CHECK (max_steps > 0),
            max_turns INTEGER NOT NULL CHECK (max_turns > 0),
            max_tokens INTEGER NOT NULL CHECK (max_tokens > 0),
            max_cost_microusd INTEGER NOT NULL CHECK (max_cost_microusd > 0),
            warning_remaining_steps INTEGER NOT NULL CHECK (warning_remaining_steps >= 0),
            warning_remaining_turns INTEGER NOT NULL CHECK (warning_remaining_turns >= 0),
            reservation_timeout_seconds INTEGER NOT NULL CHECK (reservation_timeout_seconds > 0),
            consumed_steps INTEGER NOT NULL CHECK (consumed_steps >= 0),
            consumed_turns INTEGER NOT NULL CHECK (consumed_turns >= 0),
            reserved_tokens INTEGER NOT NULL CHECK (reserved_tokens >= 0),
            reserved_cost_microusd INTEGER NOT NULL CHECK (reserved_cost_microusd >= 0),
            actual_tokens INTEGER NOT NULL CHECK (actual_tokens >= 0),
            actual_cost_microusd INTEGER NOT NULL CHECK (actual_cost_microusd >= 0),
            state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'EXHAUSTED', 'CANCELLED', 'BLOCKED_RECONCILIATION')),
            version INTEGER NOT NULL CHECK (version > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, run_id, task_id, agent_id),
            UNIQUE (tenant_id, project_id, admission_idempotency_key)
        )
    """.strip(),
    "budget_steps": """
        CREATE TABLE budget_steps (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            reservation_idempotency_key TEXT NOT NULL,
            reservation_request_sha256 TEXT NOT NULL,
            reservation_sha256 TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('RESERVED', 'SETTLED')),
            side_effect INTEGER NOT NULL CHECK (side_effect IN (0, 1)),
            estimated_tokens INTEGER NOT NULL CHECK (estimated_tokens >= 0),
            estimated_cost_microusd INTEGER NOT NULL CHECK (estimated_cost_microusd >= 0),
            actual_tokens INTEGER CHECK (actual_tokens >= 0),
            actual_cost_microusd INTEGER CHECK (actual_cost_microusd >= 0),
            outcome TEXT CHECK (outcome IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'UNKNOWN')),
            failure_type TEXT,
            remaining_work_json TEXT NOT NULL,
            blockers_json TEXT NOT NULL,
            settlement_remaining_work_json TEXT,
            settlement_blockers_json TEXT,
            reserved_at TEXT NOT NULL,
            settled_at TEXT,
            PRIMARY KEY (tenant_id, project_id, run_id, task_id, agent_id, step_id),
            UNIQUE (tenant_id, project_id, reservation_idempotency_key),
            FOREIGN KEY (tenant_id, project_id, run_id, task_id, agent_id)
                REFERENCES agent_budgets (tenant_id, project_id, run_id, task_id, agent_id)
        )
    """.strip(),
    "budget_operations": """
        CREATE TABLE budget_operations (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            operation TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            response_sha256 TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, run_id, task_id, agent_id, idempotency_key),
            FOREIGN KEY (tenant_id, project_id, run_id, task_id, agent_id)
                REFERENCES agent_budgets (tenant_id, project_id, run_id, task_id, agent_id)
        )
    """.strip(),
    "budget_events": """
        CREATE TABLE budget_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            authorization_id TEXT NOT NULL,
            budget_version INTEGER NOT NULL,
            occurred_at TEXT NOT NULL,
            previous_sha256 TEXT,
            event_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (tenant_id, project_id, run_id, task_id, agent_id)
                REFERENCES agent_budgets (tenant_id, project_id, run_id, task_id, agent_id)
        )
    """.strip(),
}
_SCHEMA_TRIGGER_SQL = {
    "agent_budgets_no_delete": """
        CREATE TRIGGER agent_budgets_no_delete
        BEFORE DELETE ON agent_budgets
        BEGIN
            SELECT RAISE(ABORT, 'agent budgets cannot be deleted');
        END
    """.strip(),
    "budget_steps_no_delete": """
        CREATE TRIGGER budget_steps_no_delete
        BEFORE DELETE ON budget_steps
        BEGIN
            SELECT RAISE(ABORT, 'budget steps cannot be deleted');
        END
    """.strip(),
    "budget_operations_no_update": """
        CREATE TRIGGER budget_operations_no_update
        BEFORE UPDATE ON budget_operations
        BEGIN
            SELECT RAISE(ABORT, 'budget operations are append-only');
        END
    """.strip(),
    "budget_operations_no_delete": """
        CREATE TRIGGER budget_operations_no_delete
        BEFORE DELETE ON budget_operations
        BEGIN
            SELECT RAISE(ABORT, 'budget operations are append-only');
        END
    """.strip(),
    "budget_events_no_update": """
        CREATE TRIGGER budget_events_no_update
        BEFORE UPDATE ON budget_events
        BEGIN
            SELECT RAISE(ABORT, 'budget events are append-only');
        END
    """.strip(),
    "budget_events_no_delete": """
        CREATE TRIGGER budget_events_no_delete
        BEFORE DELETE ON budget_events
        BEGIN
            SELECT RAISE(ABORT, 'budget events are append-only');
        END
    """.strip(),
}
_TRIGGER_TARGETS = {
    "agent_budgets_no_delete": "agent_budgets",
    "budget_steps_no_delete": "budget_steps",
    "budget_operations_no_update": "budget_operations",
    "budget_operations_no_delete": "budget_operations",
    "budget_events_no_update": "budget_events",
    "budget_events_no_delete": "budget_events",
}
_SCHEMA_DDL = ";\n\n".join((*_SCHEMA_TABLE_SQL.values(), *_SCHEMA_TRIGGER_SQL.values())) + ";"
_SCHEMA_CONTRACT = {
    "schema_id": STATE_SCHEMA_ID,
    "version": STATE_SCHEMA_VERSION,
    "tables": {name: _normalize_schema_sql(sql) for name, sql in _SCHEMA_TABLE_SQL.items()},
    "triggers": {
        name: {"table": _TRIGGER_TARGETS[name], "sql": _normalize_schema_sql(sql)}
        for name, sql in _SCHEMA_TRIGGER_SQL.items()
    },
}
STATE_SCHEMA_SHA256 = sha256_digest(canonical_bytes(_SCHEMA_CONTRACT))


def _fail(message: str, **details: object) -> None:
    raise StepBudgetValidationError(message, details=details)


def _exact_fields(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        _fail(
            f"{label} has an invalid field set",
            missing=sorted(expected - actual),
            extra=sorted(actual - expected),
        )
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        _fail(f"{label} is not a valid bounded identifier")
    return value


def _bounded_string(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail(f"{label} must be a non-empty string of at most {maximum} characters")
    return value


def _integer(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _fail(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        _fail(f"{label} must be an array of at most 32 items")
    result = [
        _bounded_string(item, f"{label}[{index}]", 512)
        for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        _fail(f"{label} contains duplicate values")
    return result


def _timestamp(value: object, label: str) -> datetime:
    text = _bounded_string(value, label, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        _fail(f"{label} must be an ISO-8601 timestamp")
        raise AssertionError from exc
    if parsed.tzinfo is None:
        _fail(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _now_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class BudgetScope:
    tenant_id: str
    project_id: str
    run_id: str
    task_id: str
    agent_id: str

    def values(self) -> tuple[str, str, str, str, str]:
        return (self.tenant_id, self.project_id, self.run_id, self.task_id, self.agent_id)

    def as_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
        }


@dataclass(frozen=True, slots=True)
class StepBudgetRequest:
    schema_version: str
    operation: str
    skill_name: str
    scope: BudgetScope
    actor_id: str
    idempotency_key: str
    authorization: Mapping[str, object]
    input: Mapping[str, object]
    canonical: bytes
    digest: str


AuthorizationVerifier = Callable[[Mapping[str, object]], bool]
Clock = Callable[[], datetime]


def authorization_scope_sha256(scope: BudgetScope, permission: str) -> str:
    """Bind an authorization decision to one exact budget scope and permission."""

    return sha256_digest(
        canonical_bytes({"scope": scope.as_dict(), "permission": permission})
    )


def _validate_policy(value: object) -> dict[str, object]:
    policy = _exact_fields(value, _POLICY_KEYS, "request.input.policy")
    normalized: dict[str, object] = {
        "base_max_steps": _integer(policy["base_max_steps"], "policy.base_max_steps", minimum=1, maximum=1_000_000),
        "base_max_turns": _integer(policy["base_max_turns"], "policy.base_max_turns", minimum=1, maximum=1_000_000),
        "hard_max_steps": _integer(policy["hard_max_steps"], "policy.hard_max_steps", minimum=1, maximum=1_000_000),
        "hard_max_turns": _integer(policy["hard_max_turns"], "policy.hard_max_turns", minimum=1, maximum=1_000_000),
        "complexity": _bounded_string(policy["complexity"], "policy.complexity", 16),
        "expected_step_cost_microusd": _integer(policy["expected_step_cost_microusd"], "policy.expected_step_cost_microusd", minimum=1, maximum=10**15),
        "max_cost_microusd": _integer(policy["max_cost_microusd"], "policy.max_cost_microusd", minimum=1, maximum=10**18),
        "max_tokens": _integer(policy["max_tokens"], "policy.max_tokens", minimum=1, maximum=10**15),
        "warning_remaining_steps": _integer(policy["warning_remaining_steps"], "policy.warning_remaining_steps", minimum=0, maximum=1_000_000),
        "warning_remaining_turns": _integer(policy["warning_remaining_turns"], "policy.warning_remaining_turns", minimum=0, maximum=1_000_000),
        "reservation_timeout_seconds": _integer(policy["reservation_timeout_seconds"], "policy.reservation_timeout_seconds", minimum=1, maximum=86_400),
    }
    complexity = str(normalized["complexity"])
    if complexity not in COMPLEXITY_MULTIPLIER_BPS:
        _fail("policy.complexity is unsupported", allowed=sorted(COMPLEXITY_MULTIPLIER_BPS))
    if int(normalized["hard_max_steps"]) < int(normalized["base_max_steps"]):
        _fail("policy.hard_max_steps cannot be below base_max_steps")
    if int(normalized["hard_max_turns"]) < int(normalized["base_max_turns"]):
        _fail("policy.hard_max_turns cannot be below base_max_turns")
    if int(normalized["max_cost_microusd"]) < int(normalized["expected_step_cost_microusd"]):
        _fail("policy.max_cost_microusd cannot fund one expected step")

    multiplier = COMPLEXITY_MULTIPLIER_BPS[complexity]
    complexity_steps = max(1, (int(normalized["base_max_steps"]) * multiplier + 9_999) // 10_000)
    complexity_turns = max(1, (int(normalized["base_max_turns"]) * multiplier + 9_999) // 10_000)
    cost_limited_steps = int(normalized["max_cost_microusd"]) // int(normalized["expected_step_cost_microusd"])
    effective_steps = min(int(normalized["hard_max_steps"]), complexity_steps, cost_limited_steps)
    effective_turns = min(int(normalized["hard_max_turns"]), complexity_turns)
    if effective_steps < 1 or effective_turns < 1:
        _fail("policy produces an unusable effective budget")
    if int(normalized["warning_remaining_steps"]) > effective_steps:
        _fail("policy.warning_remaining_steps exceeds the effective step budget")
    if int(normalized["warning_remaining_turns"]) > effective_turns:
        _fail("policy.warning_remaining_turns exceeds the effective turn budget")
    normalized["complexity_multiplier_bps"] = multiplier
    normalized["effective_max_steps"] = effective_steps
    normalized["effective_max_turns"] = effective_turns
    return normalized


def validate_step_budget_request(value: object) -> StepBudgetRequest:
    """Validate and canonicalize the exact public request contract."""

    try:
        validate_json_value(value)
    except RequestValidationError as error:
        raise StepBudgetValidationError(str(error)) from error
    request = _exact_fields(value, _REQUEST_KEYS, "request")
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        _fail("unsupported request.schema_version")
    if request["skill_name"] != SKILL_NAME:
        _fail("request.skill_name must be agent-step-budget")
    operation = _bounded_string(request["operation"], "request.operation", 16)
    if operation not in OPERATIONS:
        _fail("unsupported request.operation", allowed=sorted(OPERATIONS))
    scope = BudgetScope(
        tenant_id=_identifier(request["tenant_id"], "request.tenant_id"),
        project_id=_identifier(request["project_id"], "request.project_id"),
        run_id=_identifier(request["run_id"], "request.run_id"),
        task_id=_identifier(request["task_id"], "request.task_id"),
        agent_id=_identifier(request["agent_id"], "request.agent_id"),
    )
    actor_id = _identifier(request["actor_id"], "request.actor_id")
    idempotency_key = _identifier(request["idempotency_key"], "request.idempotency_key")

    authorization = _exact_fields(request["authorization"], _AUTHORIZATION_KEYS, "request.authorization")
    normalized_authorization: dict[str, object] = {
        "authorization_id": _identifier(authorization["authorization_id"], "authorization.authorization_id"),
        "decision": _bounded_string(authorization["decision"], "authorization.decision", 16),
        "permission": _bounded_string(authorization["permission"], "authorization.permission", 64),
        "subject_actor_id": _identifier(authorization["subject_actor_id"], "authorization.subject_actor_id"),
        "scope_sha256": _bounded_string(authorization["scope_sha256"], "authorization.scope_sha256", 71),
        "issued_at": _bounded_string(authorization["issued_at"], "authorization.issued_at", 64),
        "expires_at": _bounded_string(authorization["expires_at"], "authorization.expires_at", 64),
        "token": _bounded_string(authorization["token"], "authorization.token", 4096),
    }
    if normalized_authorization["decision"] not in {"ALLOW", "DENY"}:
        _fail("authorization.decision must be ALLOW or DENY")
    if normalized_authorization["permission"] not in set(PERMISSIONS.values()):
        _fail("authorization.permission is unsupported")
    if not _DIGEST_RE.fullmatch(str(normalized_authorization["scope_sha256"])):
        _fail("authorization.scope_sha256 must be a SHA-256 digest")

    raw_input = _exact_fields(request["input"], _INPUT_KEYS[operation], "request.input")
    normalized_input: dict[str, object]
    if operation == "admit":
        normalized_input = {"policy": _validate_policy(raw_input["policy"])}
    elif operation == "reserve":
        if not isinstance(raw_input["side_effect"], bool):
            _fail("request.input.side_effect must be a boolean")
        normalized_input = {
            "expected_version": _integer(raw_input["expected_version"], "input.expected_version", minimum=1, maximum=10**12),
            "step_id": _identifier(raw_input["step_id"], "input.step_id"),
            "turn_id": _identifier(raw_input["turn_id"], "input.turn_id"),
            "estimated_tokens": _integer(raw_input["estimated_tokens"], "input.estimated_tokens", minimum=0, maximum=10**15),
            "estimated_cost_microusd": _integer(raw_input["estimated_cost_microusd"], "input.estimated_cost_microusd", minimum=0, maximum=10**18),
            "side_effect": raw_input["side_effect"],
            "remaining_work": _string_list(raw_input["remaining_work"], "input.remaining_work"),
            "blockers": _string_list(raw_input["blockers"], "input.blockers"),
        }
    elif operation == "settle":
        outcome = _bounded_string(raw_input["outcome"], "input.outcome", 16)
        if outcome not in SETTLEMENT_OUTCOMES:
            _fail("input.outcome is unsupported", allowed=sorted(SETTLEMENT_OUTCOMES))
        failure_type = raw_input["failure_type"]
        if outcome in {"FAILED", "UNKNOWN"}:
            if not isinstance(failure_type, str) or not _FAILURE_RE.fullmatch(failure_type):
                _fail("input.failure_type is required for FAILED or UNKNOWN outcomes")
        elif failure_type is not None:
            _fail("input.failure_type must be null for SUCCEEDED or CANCELLED outcomes")
        normalized_input = {
            "expected_version": _integer(raw_input["expected_version"], "input.expected_version", minimum=1, maximum=10**12),
            "step_id": _identifier(raw_input["step_id"], "input.step_id"),
            "outcome": outcome,
            "actual_tokens": _integer(raw_input["actual_tokens"], "input.actual_tokens", minimum=0, maximum=10**15),
            "actual_cost_microusd": _integer(raw_input["actual_cost_microusd"], "input.actual_cost_microusd", minimum=0, maximum=10**18),
            "failure_type": failure_type,
            "remaining_work": _string_list(raw_input["remaining_work"], "input.remaining_work"),
            "blockers": _string_list(raw_input["blockers"], "input.blockers"),
        }
    elif operation == "cancel":
        normalized_input = {
            "expected_version": _integer(raw_input["expected_version"], "input.expected_version", minimum=1, maximum=10**12),
            "reason": _bounded_string(raw_input["reason"], "input.reason", 1024),
        }
    elif operation == "audit":
        normalized_input = {
            "after_sequence": _integer(raw_input["after_sequence"], "input.after_sequence", minimum=0, maximum=10**18),
            "limit": _integer(raw_input["limit"], "input.limit", minimum=1, maximum=1000),
        }
    else:
        normalized_input = {}

    normalized = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "operation": operation,
        "skill_name": SKILL_NAME,
        **scope.as_dict(),
        "actor_id": actor_id,
        "idempotency_key": idempotency_key,
        "authorization": normalized_authorization,
        "input": normalized_input,
    }
    canonical = canonical_bytes(normalized)
    if len(canonical) > 65_536:
        _fail("canonical request exceeds 65536 bytes")
    return StepBudgetRequest(
        schema_version=REQUEST_SCHEMA_VERSION,
        operation=operation,
        skill_name=SKILL_NAME,
        scope=scope,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        authorization=MappingProxyType(normalized_authorization),
        input=MappingProxyType(normalized_input),
        canonical=canonical,
        digest=sha256_digest(canonical),
    )


class StepBudgetStore:
    """SQLite-backed Agent/task step budget with optimistic concurrency."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        authorization_verifier: AuthorizationVerifier | None,
        clock: Clock | None = None,
        create: bool = True,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.authorization_verifier = authorization_verifier
        self.clock = clock or (lambda: datetime.now(UTC))
        if not self.database_path.parent.is_dir():
            raise StepBudgetConflict("budget database parent directory does not exist")
        if create:
            self._initialize()
        elif not self.database_path.is_file():
            raise StepBudgetNotFound("budget database does not exist")
        else:
            self._validate_existing_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
        except BaseException:
            connection.close()
            raise
        return connection

    def _initialize(self) -> None:
        if self.database_path.exists():
            self._validate_existing_schema()
            return
        with closing(self._connect()) as connection, connection:
            connection.executescript(_SCHEMA_DDL)
            connection.execute(
                "INSERT INTO budget_schema (schema_id, version, schema_sha256, created_at) VALUES (?, ?, ?, ?)",
                (STATE_SCHEMA_ID, STATE_SCHEMA_VERSION, STATE_SCHEMA_SHA256, _now_text(self.clock())),
            )
            connection.execute(f"PRAGMA user_version = {STATE_SCHEMA_VERSION}")
        os.chmod(self.database_path, 0o600)
        self._validate_existing_schema()

    def _validate_existing_schema(self) -> None:
        expected = {
            *(("table", name) for name in _SCHEMA_TABLE_SQL),
            *(("trigger", name) for name in _SCHEMA_TRIGGER_SQL),
        }
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT type, name, tbl_name, sql
                    FROM sqlite_master
                    WHERE type IN ('table', 'index', 'trigger', 'view')
                    ORDER BY type, name
                    """
                ).fetchall()
                user_rows = [row for row in rows if not str(row[1]).startswith("sqlite_")]
                actual = {(str(row[0]), str(row[1])) for row in user_rows}
                if actual != expected:
                    raise StepBudgetSchemaMigrationRequired(
                        "budget schema objects drifted; automatic migration is forbidden",
                        details={"missing": sorted(expected - actual), "unexpected": sorted(actual - expected)},
                    )
                by_object = {(str(row[0]), str(row[1])): row for row in user_rows}
                for table, sql in _SCHEMA_TABLE_SQL.items():
                    row = by_object[("table", table)]
                    if str(row[2]) != table or _normalize_schema_sql(str(row[3])) != _normalize_schema_sql(sql):
                        raise StepBudgetSchemaMigrationRequired(
                            "budget table definition drift requires an explicit migration",
                            details={"table": table},
                        )
                for trigger, sql in _SCHEMA_TRIGGER_SQL.items():
                    row = by_object[("trigger", trigger)]
                    if str(row[2]) != _TRIGGER_TARGETS[trigger] or _normalize_schema_sql(str(row[3])) != _normalize_schema_sql(sql):
                        raise StepBudgetSchemaMigrationRequired(
                            "budget trigger definition drift requires an explicit migration",
                            details={"trigger": trigger},
                        )
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                metadata = connection.execute(
                    "SELECT schema_id, version, schema_sha256 FROM budget_schema"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise StepBudgetSchemaMigrationRequired(
                "budget schema could not be validated",
                details={"sqlite_error": type(exc).__name__},
            ) from exc
        if version != STATE_SCHEMA_VERSION or len(metadata) != 1 or tuple(metadata[0]) != (
            STATE_SCHEMA_ID,
            STATE_SCHEMA_VERSION,
            STATE_SCHEMA_SHA256,
        ):
            raise StepBudgetSchemaMigrationRequired(
                "budget schema metadata is incompatible; automatic migration is forbidden"
            )

    def _authorize(self, request: StepBudgetRequest) -> None:
        authorization = request.authorization
        permission = PERMISSIONS[request.operation]
        expected_scope = authorization_scope_sha256(request.scope, permission)
        issued_at = _timestamp(authorization["issued_at"], "authorization.issued_at")
        expires_at = _timestamp(authorization["expires_at"], "authorization.expires_at")
        now = self.clock().astimezone(UTC)
        structural_denial = (
            authorization["decision"] != "ALLOW"
            or authorization["permission"] != permission
            or authorization["subject_actor_id"] != request.actor_id
            or authorization["scope_sha256"] != expected_scope
            or issued_at > now
            or expires_at <= now
            or expires_at <= issued_at
            or (expires_at - issued_at).total_seconds() > 900
        )
        if structural_denial:
            raise StepBudgetAuthorizationDenied(
                "authorization is denied, expired, overlong, or not bound to the exact scope",
                details={"operation": request.operation, "permission": permission},
            )
        if self.authorization_verifier is None:
            raise StepBudgetAuthorizationDenied(
                "an external authorization verifier adapter is required before budget access"
            )
        try:
            trusted = self.authorization_verifier(MappingProxyType(dict(authorization)))
        except Exception as exc:
            raise StepBudgetAuthorizationDenied(
                "authorization verifier failed closed",
                details={"verifier_error": type(exc).__name__},
            ) from exc
        if trusted is not True:
            raise StepBudgetAuthorizationDenied("authorization verifier rejected the decision")

    def execute(self, value: object) -> dict[str, object]:
        """Execute one strict, authorized budget operation."""

        request = validate_step_budget_request(value)
        self._authorize(request)
        handler = {
            "admit": self._admit,
            "reserve": self._reserve,
            "settle": self._settle,
            "status": self._status,
            "cancel": self._cancel,
            "audit": self._audit,
        }[request.operation]
        return handler(request)

    @staticmethod
    def _budget_row(connection: sqlite3.Connection, scope: BudgetScope) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM agent_budgets
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
            """,
            scope.values(),
        ).fetchone()
        if row is None:
            raise StepBudgetNotFound("agent/task budget does not exist")
        policy_text = str(row["policy_json"])
        try:
            policy = json.loads(policy_text)
        except json.JSONDecodeError as exc:
            raise StepBudgetConflict("stored budget policy is invalid JSON") from exc
        if canonical_json(policy) != policy_text or sha256_digest(policy_text.encode("utf-8")) != row["policy_sha256"]:
            raise StepBudgetConflict("stored budget policy digest integrity check failed")
        return row

    @staticmethod
    def _budget_state(row: sqlite3.Row) -> dict[str, object]:
        integer_fields = (
            "max_steps",
            "max_turns",
            "max_tokens",
            "max_cost_microusd",
            "warning_remaining_steps",
            "warning_remaining_turns",
            "reservation_timeout_seconds",
            "consumed_steps",
            "consumed_turns",
            "reserved_tokens",
            "reserved_cost_microusd",
            "actual_tokens",
            "actual_cost_microusd",
            "version",
        )
        return {
            "policy_sha256": row["policy_sha256"],
            **{field: int(row[field]) for field in integer_fields},
            "state": row["state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _replay(
        connection: sqlite3.Connection,
        request: StepBudgetRequest,
    ) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT operation, request_sha256, response_sha256, response_json
            FROM budget_operations
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ?
              AND agent_id = ? AND idempotency_key = ?
            """,
            (*request.scope.values(), request.idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if row["operation"] != request.operation or row["request_sha256"] != request.digest:
            raise IdempotencyConflict(
                "idempotency key is already bound to different budget content",
                details={"idempotency_key": request.idempotency_key},
            )
        response_text = str(row["response_json"])
        try:
            response = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise StepBudgetConflict("stored idempotent response is invalid JSON") from exc
        if canonical_json(response) != response_text or sha256_digest(response_text.encode("utf-8")) != row["response_sha256"]:
            raise StepBudgetConflict("stored idempotent response digest integrity check failed")
        response["replayed"] = True
        return response

    def _record_operation(
        self,
        connection: sqlite3.Connection,
        request: StepBudgetRequest,
        response: dict[str, object],
    ) -> None:
        response_text = canonical_json(response)
        connection.execute(
            """
            INSERT INTO budget_operations (
                tenant_id, project_id, run_id, task_id, agent_id,
                idempotency_key, operation, request_sha256,
                response_sha256, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                *request.scope.values(),
                request.idempotency_key,
                request.operation,
                request.digest,
                sha256_digest(response_text.encode("utf-8")),
                response_text,
                _now_text(self.clock()),
            ),
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        request: StepBudgetRequest,
        *,
        event_type: str,
        budget_version: int,
        payload: dict[str, object],
    ) -> str:
        previous = connection.execute(
            """
            SELECT event_sha256 FROM budget_events
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
            ORDER BY sequence DESC LIMIT 1
            """,
            request.scope.values(),
        ).fetchone()
        previous_sha256 = str(previous[0]) if previous else None
        occurred_at = _now_text(self.clock())
        budget_row = self._budget_row(connection, request.scope)
        bound_payload = {**payload, "budget_state": self._budget_state(budget_row)}
        body = {
            "scope": request.scope.as_dict(),
            "event_type": event_type,
            "actor_id": request.actor_id,
            "authorization_id": request.authorization["authorization_id"],
            "budget_version": budget_version,
            "occurred_at": occurred_at,
            "previous_sha256": previous_sha256,
            "payload": bound_payload,
        }
        event_sha256 = sha256_digest(canonical_bytes(body))
        connection.execute(
            """
            INSERT INTO budget_events (
                tenant_id, project_id, run_id, task_id, agent_id,
                event_type, actor_id, authorization_id, budget_version,
                occurred_at, previous_sha256, event_sha256, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                *request.scope.values(),
                event_type,
                request.actor_id,
                request.authorization["authorization_id"],
                budget_version,
                occurred_at,
                previous_sha256,
                event_sha256,
                canonical_json(bound_payload),
            ),
        )
        return event_sha256

    @staticmethod
    def _verify_event_chain(connection: sqlite3.Connection, scope: BudgetScope) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT * FROM budget_events
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
            ORDER BY sequence
            """,
            scope.values(),
        ).fetchall()
        previous_sha256: str | None = None
        result: list[dict[str, object]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError as exc:
                raise StepBudgetConflict("stored budget event payload is invalid JSON") from exc
            if canonical_json(payload) != row["payload_json"] or row["previous_sha256"] != previous_sha256:
                raise StepBudgetConflict("budget event chain integrity check failed")
            body = {
                "scope": scope.as_dict(),
                "event_type": row["event_type"],
                "actor_id": row["actor_id"],
                "authorization_id": row["authorization_id"],
                "budget_version": row["budget_version"],
                "occurred_at": row["occurred_at"],
                "previous_sha256": previous_sha256,
                "payload": payload,
            }
            expected = sha256_digest(canonical_bytes(body))
            if row["event_sha256"] != expected:
                raise StepBudgetConflict("budget event digest integrity check failed")
            previous_sha256 = expected
            result.append(
                {
                    "sequence": int(row["sequence"]),
                    **body,
                    "event_sha256": expected,
                }
            )
        return result

    def _snapshot(
        self,
        connection: sqlite3.Connection,
        request: StepBudgetRequest,
        *,
        remaining_work: list[str] | None = None,
        blockers: list[str] | None = None,
    ) -> dict[str, object]:
        row = self._budget_row(connection, request.scope)
        aggregates = connection.execute(
            """
            SELECT
                COUNT(*) AS consumed_steps,
                COUNT(DISTINCT turn_id) AS consumed_turns,
                COALESCE(SUM(estimated_tokens), 0) AS reserved_tokens,
                COALESCE(SUM(estimated_cost_microusd), 0) AS reserved_cost_microusd,
                COALESCE(SUM(actual_tokens), 0) AS actual_tokens,
                COALESCE(SUM(actual_cost_microusd), 0) AS actual_cost_microusd
            FROM budget_steps
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
            """,
            request.scope.values(),
        ).fetchone()
        counter_fields = (
            "consumed_steps",
            "consumed_turns",
            "reserved_tokens",
            "reserved_cost_microusd",
            "actual_tokens",
            "actual_cost_microusd",
        )
        if any(int(row[field]) != int(aggregates[field]) for field in counter_fields):
            raise StepBudgetConflict("budget usage counters do not match durable steps")
        events = self._verify_event_chain(connection, request.scope)
        if not events or int(events[-1]["budget_version"]) != int(row["version"]):
            raise StepBudgetConflict("budget version is not bound to the audit chain")
        if events[-1]["payload"].get("budget_state") != self._budget_state(row):
            raise StepBudgetConflict("current budget state is not bound to the audit chain head")

        step_rows = connection.execute(
            """
            SELECT * FROM budget_steps
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
            ORDER BY reserved_at, step_id
            """,
            request.scope.values(),
        ).fetchall()
        reserved_events = {
            str(event["payload"].get("step_id")): event["payload"]
            for event in events
            if event["event_type"] == "STEP_RESERVED"
        }
        settled_events = {
            str(event["payload"].get("step_id")): event["payload"]
            for event in events
            if event["event_type"] == "STEP_SETTLED"
        }
        if len(reserved_events) != len(step_rows):
            raise StepBudgetConflict("durable steps do not match reservation audit events")
        for step in step_rows:
            step_id = str(step["step_id"])
            try:
                reservation_remaining = json.loads(str(step["remaining_work_json"]))
                reservation_blockers = json.loads(str(step["blockers_json"]))
            except json.JSONDecodeError as exc:
                raise StepBudgetConflict("stored reservation context is invalid JSON") from exc
            expected_reservation = {
                "step_id": step_id,
                "turn_id": step["turn_id"],
                "reservation_request_sha256": step["reservation_request_sha256"],
                "reservation_sha256": step["reservation_sha256"],
                "side_effect": bool(step["side_effect"]),
                "estimated_tokens": int(step["estimated_tokens"]),
                "estimated_cost_microusd": int(step["estimated_cost_microusd"]),
                "remaining_work": reservation_remaining,
                "blockers": reservation_blockers,
                "reserved_at": step["reserved_at"],
            }
            actual_reservation = reserved_events.get(step_id)
            if actual_reservation is None or any(
                actual_reservation.get(field) != value
                for field, value in expected_reservation.items()
            ):
                raise StepBudgetConflict("step reservation is not bound to its audit event")
            reservation_body = {
                "scope": request.scope.as_dict(),
                "step_id": step_id,
                "turn_id": step["turn_id"],
                "request_sha256": step["reservation_request_sha256"],
                "reserved_at": step["reserved_at"],
                "side_effect": bool(step["side_effect"]),
            }
            if sha256_digest(canonical_bytes(reservation_body)) != step["reservation_sha256"]:
                raise StepBudgetConflict("step reservation digest integrity check failed")
            if step["state"] == "RESERVED":
                if step_id in settled_events:
                    raise StepBudgetConflict("reserved step unexpectedly has a settlement event")
                continue
            try:
                settlement_remaining = json.loads(str(step["settlement_remaining_work_json"]))
                settlement_blockers = json.loads(str(step["settlement_blockers_json"]))
            except (json.JSONDecodeError, TypeError) as exc:
                raise StepBudgetConflict("stored settlement context is invalid JSON") from exc
            expected_settlement = {
                "step_id": step_id,
                "outcome": step["outcome"],
                "failure_type": step["failure_type"],
                "actual_tokens": int(step["actual_tokens"]),
                "actual_cost_microusd": int(step["actual_cost_microusd"]),
                "remaining_work": settlement_remaining,
                "blockers": settlement_blockers,
                "settled_at": step["settled_at"],
            }
            actual_settlement = settled_events.get(step_id)
            if actual_settlement is None or any(
                actual_settlement.get(field) != value
                for field, value in expected_settlement.items()
            ):
                raise StepBudgetConflict("step settlement is not bound to its audit event")

        pending = connection.execute(
            """
            SELECT * FROM budget_steps
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
              AND state = 'RESERVED'
            ORDER BY reserved_at, step_id
            """,
            request.scope.values(),
        ).fetchall()
        if len(pending) > 1:
            raise StepBudgetConflict("more than one unsettled step violates the serial settlement contract")
        latest = connection.execute(
            """
            SELECT * FROM budget_steps
            WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
            ORDER BY reserved_at DESC, step_id DESC LIMIT 1
            """,
            request.scope.values(),
        ).fetchone()
        if remaining_work is None and latest is not None:
            source = latest["settlement_remaining_work_json"] or latest["remaining_work_json"]
            remaining_work = json.loads(str(source))
        if blockers is None and latest is not None:
            source = latest["settlement_blockers_json"] or latest["blockers_json"]
            blockers = json.loads(str(source))
        remaining_work = remaining_work or []
        blockers = blockers or []

        remaining_steps = max(0, int(row["max_steps"]) - int(row["consumed_steps"]))
        remaining_turns = max(0, int(row["max_turns"]) - int(row["consumed_turns"]))
        remaining_tokens = max(0, int(row["max_tokens"]) - int(row["reserved_tokens"]))
        remaining_cost = max(0, int(row["max_cost_microusd"]) - int(row["reserved_cost_microusd"]))
        near_limit = (
            remaining_steps <= int(row["warning_remaining_steps"])
            or remaining_turns <= int(row["warning_remaining_turns"])
        )

        state = str(row["state"])
        stop_reason: str | None = None
        decision = "CONTINUE"
        pending_value: dict[str, object] | None = None
        if pending:
            pending_row = pending[0]
            reserved_at = _timestamp(pending_row["reserved_at"], "stored.reserved_at")
            age_seconds = max(0, int((self.clock().astimezone(UTC) - reserved_at).total_seconds()))
            timed_out = age_seconds > int(row["reservation_timeout_seconds"])
            decision = "WAIT_FOR_SETTLEMENT"
            stop_reason = "RESERVATION_TIMEOUT_REQUIRES_RECONCILIATION" if timed_out else "PENDING_STEP_SETTLEMENT"
            pending_value = {
                "step_id": pending_row["step_id"],
                "turn_id": pending_row["turn_id"],
                "reservation_sha256": pending_row["reservation_sha256"],
                "side_effect": bool(pending_row["side_effect"]),
                "reserved_at": pending_row["reserved_at"],
                "age_seconds": age_seconds,
                "timed_out": timed_out,
            }
        elif state == BLOCKED_RECONCILIATION:
            decision = "BLOCKED"
            stop_reason = "UNRECONCILED_EXTERNAL_OUTCOME"
        elif state == CANCELLED:
            decision = "STOP"
            stop_reason = "CANCELLED"
        elif state == EXHAUSTED:
            decision = "STOP"
            if int(row["actual_cost_microusd"]) >= int(row["max_cost_microusd"]):
                stop_reason = "COST_LIMIT_REACHED"
            elif int(row["actual_tokens"]) >= int(row["max_tokens"]):
                stop_reason = "TOKEN_LIMIT_REACHED"
            elif remaining_steps == 0:
                stop_reason = "STEP_LIMIT_REACHED"
            else:
                stop_reason = "TURN_LIMIT_REACHED"

        outcomes = {
            str(item["outcome"]): int(item["count"])
            for item in connection.execute(
                """
                SELECT outcome, COUNT(*) AS count FROM budget_steps
                WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                  AND state = 'SETTLED'
                GROUP BY outcome
                """,
                request.scope.values(),
            ).fetchall()
        }
        failure_types = {
            str(item["failure_type"]): int(item["count"])
            for item in connection.execute(
                """
                SELECT failure_type, COUNT(*) AS count FROM budget_steps
                WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                  AND failure_type IS NOT NULL
                GROUP BY failure_type
                """,
                request.scope.values(),
            ).fetchall()
        }
        elapsed_ms = max(
            0,
            int((self.clock().astimezone(UTC) - _timestamp(row["created_at"], "stored.created_at")).total_seconds() * 1000),
        )
        policy = json.loads(str(row["policy_json"]))
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "runtime_version": RUNTIME_VERSION,
            "skill_name": SKILL_NAME,
            "operation": request.operation,
            "request_sha256": request.digest,
            "decision": decision,
            "stop_reason": stop_reason,
            "state": state,
            "scope": request.scope.as_dict(),
            "policy_sha256": row["policy_sha256"],
            "policy": policy,
            "usage": {field: int(row[field]) for field in counter_fields},
            "remaining": {
                "steps": remaining_steps,
                "turns": remaining_turns,
                "tokens": remaining_tokens,
                "cost_microusd": remaining_cost,
            },
            "near_limit": near_limit,
            "remaining_work": remaining_work,
            "blockers": blockers,
            "pending_step": pending_value,
            "version": int(row["version"]),
            "audit": {
                "event_count": len(events),
                "head_sha256": events[-1]["event_sha256"],
            },
            "metrics": {
                "settled_steps": sum(outcomes.values()),
                "success_count": outcomes.get("SUCCEEDED", 0),
                "outcomes": outcomes,
                "failure_types": failure_types,
                "elapsed_ms": elapsed_ms,
                "tokens": int(row["actual_tokens"]),
                "cost_microusd": int(row["actual_cost_microusd"]),
            },
            "replayed": False,
            "control_plane_execution_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "domain_runtime_evidence_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "customer_evidence_status": NOT_RUN,
            "external_evidence_status": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "side_effects_performed": False,
        }

    def _admit(self, request: StepBudgetRequest) -> dict[str, object]:
        policy = dict(request.input["policy"])
        policy_text = canonical_json(policy)
        policy_sha256 = sha256_digest(policy_text.encode("utf-8"))
        now = _now_text(self.clock())
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = self._replay(connection, request)
                if replay is not None:
                    connection.commit()
                    return replay
                existing = connection.execute(
                    """
                    SELECT policy_sha256 FROM agent_budgets
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                    """,
                    request.scope.values(),
                ).fetchone()
                if existing is not None:
                    raise StepBudgetConflict(
                        "budget scope was already admitted under a different idempotency identity",
                        details={"same_policy": existing["policy_sha256"] == policy_sha256},
                    )
                connection.execute(
                    """
                    INSERT INTO agent_budgets (
                        tenant_id, project_id, run_id, task_id, agent_id,
                        admission_idempotency_key, policy_sha256, policy_json,
                        max_steps, max_turns, max_tokens, max_cost_microusd,
                        warning_remaining_steps, warning_remaining_turns,
                        reservation_timeout_seconds, consumed_steps, consumed_turns,
                        reserved_tokens, reserved_cost_microusd, actual_tokens,
                        actual_cost_microusd, state, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 'ACTIVE', 1, ?, ?)
                    """,
                    (
                        *request.scope.values(),
                        request.idempotency_key,
                        policy_sha256,
                        policy_text,
                        policy["effective_max_steps"],
                        policy["effective_max_turns"],
                        policy["max_tokens"],
                        policy["max_cost_microusd"],
                        policy["warning_remaining_steps"],
                        policy["warning_remaining_turns"],
                        policy["reservation_timeout_seconds"],
                        now,
                        now,
                    ),
                )
                self._append_event(
                    connection,
                    request,
                    event_type="BUDGET_ADMITTED",
                    budget_version=1,
                    payload={"policy_sha256": policy_sha256, "effective_max_steps": policy["effective_max_steps"], "effective_max_turns": policy["effective_max_turns"]},
                )
                response = self._snapshot(connection, request)
                self._record_operation(connection, request, response)
                connection.commit()
                return response
            except BaseException:
                connection.rollback()
                raise

    def _reserve(self, request: StepBudgetRequest) -> dict[str, object]:
        input_value = request.input
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = self._replay(connection, request)
                if replay is not None:
                    connection.commit()
                    return replay
                row = self._budget_row(connection, request.scope)
                if int(row["version"]) != int(input_value["expected_version"]):
                    raise StepBudgetConflict("budget version changed", details={"expected": input_value["expected_version"], "actual": row["version"]})
                if row["state"] != ACTIVE:
                    raise StepBudgetExhausted("budget is not active", details={"state": row["state"]})
                pending = connection.execute(
                    """
                    SELECT step_id FROM budget_steps
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                      AND state = 'RESERVED'
                    """,
                    request.scope.values(),
                ).fetchone()
                if pending is not None:
                    raise StepSettlementRequired("the prior durable step permit must be settled before another reservation", details={"step_id": pending["step_id"]})
                duplicate = connection.execute(
                    """
                    SELECT state FROM budget_steps
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ? AND step_id = ?
                    """,
                    (*request.scope.values(), input_value["step_id"]),
                ).fetchone()
                if duplicate is not None:
                    raise StepBudgetConflict("step_id is already durably bound", details={"step_id": input_value["step_id"]})
                known_turn = connection.execute(
                    """
                    SELECT 1 FROM budget_steps
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ? AND turn_id = ?
                    LIMIT 1
                    """,
                    (*request.scope.values(), input_value["turn_id"]),
                ).fetchone()
                projected_steps = int(row["consumed_steps"]) + 1
                projected_turns = int(row["consumed_turns"]) + (0 if known_turn else 1)
                projected_tokens = int(row["reserved_tokens"]) + int(input_value["estimated_tokens"])
                projected_cost = int(row["reserved_cost_microusd"]) + int(input_value["estimated_cost_microusd"])
                limits = (
                    (projected_steps > int(row["max_steps"]), "STEP_LIMIT_EXCEEDED"),
                    (projected_turns > int(row["max_turns"]), "TURN_LIMIT_EXCEEDED"),
                    (projected_tokens > int(row["max_tokens"]), "TOKEN_LIMIT_EXCEEDED"),
                    (projected_cost > int(row["max_cost_microusd"]), "COST_LIMIT_EXCEEDED"),
                )
                for exceeded, reason in limits:
                    if exceeded:
                        raise StepBudgetExhausted("step reservation exceeds the durable budget", details={"stop_reason": reason})
                remaining_steps = int(row["max_steps"]) - projected_steps
                remaining_turns = int(row["max_turns"]) - projected_turns
                near_limit = remaining_steps <= int(row["warning_remaining_steps"]) or remaining_turns <= int(row["warning_remaining_turns"])
                if near_limit and not input_value["remaining_work"]:
                    raise StepBudgetValidationError(
                        "remaining_work is required when a reservation enters the warning window",
                        details={"remaining_steps": remaining_steps, "remaining_turns": remaining_turns},
                    )
                reserved_at = _now_text(self.clock())
                reservation_body = {
                    "scope": request.scope.as_dict(),
                    "step_id": input_value["step_id"],
                    "turn_id": input_value["turn_id"],
                    "request_sha256": request.digest,
                    "reserved_at": reserved_at,
                    "side_effect": input_value["side_effect"],
                }
                reservation_sha256 = sha256_digest(canonical_bytes(reservation_body))
                connection.execute(
                    """
                    INSERT INTO budget_steps (
                        tenant_id, project_id, run_id, task_id, agent_id,
                        step_id, turn_id, reservation_idempotency_key,
                        reservation_request_sha256, reservation_sha256, state,
                        side_effect, estimated_tokens, estimated_cost_microusd,
                        remaining_work_json, blockers_json, reserved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        *request.scope.values(),
                        input_value["step_id"],
                        input_value["turn_id"],
                        request.idempotency_key,
                        request.digest,
                        reservation_sha256,
                        int(bool(input_value["side_effect"])),
                        input_value["estimated_tokens"],
                        input_value["estimated_cost_microusd"],
                        canonical_json(list(input_value["remaining_work"])),
                        canonical_json(list(input_value["blockers"])),
                        reserved_at,
                    ),
                )
                version = int(row["version"]) + 1
                connection.execute(
                    """
                    UPDATE agent_budgets SET
                        consumed_steps = ?, consumed_turns = ?, reserved_tokens = ?,
                        reserved_cost_microusd = ?, version = ?, updated_at = ?
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                    """,
                    (projected_steps, projected_turns, projected_tokens, projected_cost, version, reserved_at, *request.scope.values()),
                )
                self._append_event(
                    connection,
                    request,
                    event_type="STEP_RESERVED",
                    budget_version=version,
                    payload={
                        "step_id": input_value["step_id"],
                        "turn_id": input_value["turn_id"],
                        "reservation_request_sha256": request.digest,
                        "reservation_sha256": reservation_sha256,
                        "side_effect": input_value["side_effect"],
                        "estimated_tokens": input_value["estimated_tokens"],
                        "estimated_cost_microusd": input_value["estimated_cost_microusd"],
                        "remaining_work": list(input_value["remaining_work"]),
                        "blockers": list(input_value["blockers"]),
                        "reserved_at": reserved_at,
                    },
                )
                response = self._snapshot(
                    connection,
                    request,
                    remaining_work=list(input_value["remaining_work"]),
                    blockers=list(input_value["blockers"]),
                )
                response["permit"] = {
                    "step_id": input_value["step_id"],
                    "turn_id": input_value["turn_id"],
                    "reservation_sha256": reservation_sha256,
                    "side_effect_registered": bool(input_value["side_effect"]),
                    "execute_authorized": True,
                    "stop_after_step": remaining_steps == 0 or remaining_turns == 0,
                }
                self._record_operation(connection, request, response)
                connection.commit()
                return response
            except BaseException:
                connection.rollback()
                raise

    def _settle(self, request: StepBudgetRequest) -> dict[str, object]:
        input_value = request.input
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = self._replay(connection, request)
                if replay is not None:
                    connection.commit()
                    return replay
                row = self._budget_row(connection, request.scope)
                if int(row["version"]) != int(input_value["expected_version"]):
                    raise StepBudgetConflict("budget version changed", details={"expected": input_value["expected_version"], "actual": row["version"]})
                step = connection.execute(
                    """
                    SELECT * FROM budget_steps
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ? AND step_id = ?
                    """,
                    (*request.scope.values(), input_value["step_id"]),
                ).fetchone()
                if step is None or step["state"] != "RESERVED":
                    raise StepBudgetConflict("step is absent or already settled", details={"step_id": input_value["step_id"]})
                actual_tokens = int(row["actual_tokens"]) + int(input_value["actual_tokens"])
                actual_cost = int(row["actual_cost_microusd"]) + int(input_value["actual_cost_microusd"])
                outcome = str(input_value["outcome"])
                if outcome == "UNKNOWN":
                    state = BLOCKED_RECONCILIATION
                elif (
                    int(row["consumed_steps"]) >= int(row["max_steps"])
                    or int(row["consumed_turns"]) >= int(row["max_turns"])
                    or actual_tokens >= int(row["max_tokens"])
                    or actual_cost >= int(row["max_cost_microusd"])
                ):
                    state = EXHAUSTED
                else:
                    state = ACTIVE
                settled_at = _now_text(self.clock())
                connection.execute(
                    """
                    UPDATE budget_steps SET
                        state = 'SETTLED', actual_tokens = ?, actual_cost_microusd = ?,
                        outcome = ?, failure_type = ?, settlement_remaining_work_json = ?,
                        settlement_blockers_json = ?, settled_at = ?
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ? AND step_id = ?
                    """,
                    (
                        input_value["actual_tokens"],
                        input_value["actual_cost_microusd"],
                        outcome,
                        input_value["failure_type"],
                        canonical_json(list(input_value["remaining_work"])),
                        canonical_json(list(input_value["blockers"])),
                        settled_at,
                        *request.scope.values(),
                        input_value["step_id"],
                    ),
                )
                version = int(row["version"]) + 1
                connection.execute(
                    """
                    UPDATE agent_budgets SET actual_tokens = ?, actual_cost_microusd = ?,
                        state = ?, version = ?, updated_at = ?
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                    """,
                    (actual_tokens, actual_cost, state, version, settled_at, *request.scope.values()),
                )
                self._append_event(
                    connection,
                    request,
                    event_type="STEP_SETTLED",
                    budget_version=version,
                    payload={
                        "step_id": input_value["step_id"],
                        "outcome": outcome,
                        "failure_type": input_value["failure_type"],
                        "actual_tokens": input_value["actual_tokens"],
                        "actual_cost_microusd": input_value["actual_cost_microusd"],
                        "remaining_work": list(input_value["remaining_work"]),
                        "blockers": list(input_value["blockers"]),
                        "settled_at": settled_at,
                    },
                )
                response = self._snapshot(
                    connection,
                    request,
                    remaining_work=list(input_value["remaining_work"]),
                    blockers=list(input_value["blockers"]),
                )
                response["settlement"] = {
                    "step_id": input_value["step_id"],
                    "outcome": outcome,
                    "failure_type": input_value["failure_type"],
                    "external_step_outcome_recorded": True,
                }
                self._record_operation(connection, request, response)
                connection.commit()
                return response
            except BaseException:
                connection.rollback()
                raise

    def _status(self, request: StepBudgetRequest) -> dict[str, object]:
        with closing(self._connect()) as connection:
            return self._snapshot(connection, request)

    def _cancel(self, request: StepBudgetRequest) -> dict[str, object]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = self._replay(connection, request)
                if replay is not None:
                    connection.commit()
                    return replay
                row = self._budget_row(connection, request.scope)
                if int(row["version"]) != int(request.input["expected_version"]):
                    raise StepBudgetConflict("budget version changed", details={"expected": request.input["expected_version"], "actual": row["version"]})
                pending = connection.execute(
                    """
                    SELECT step_id FROM budget_steps
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ? AND state = 'RESERVED'
                    """,
                    request.scope.values(),
                ).fetchone()
                if pending is not None:
                    raise StepSettlementRequired("cannot cancel while a durable step outcome is unknown", details={"step_id": pending["step_id"]})
                if row["state"] == CANCELLED:
                    raise StepBudgetConflict("budget is already cancelled")
                version = int(row["version"]) + 1
                occurred_at = _now_text(self.clock())
                connection.execute(
                    """
                    UPDATE agent_budgets SET state = 'CANCELLED', version = ?, updated_at = ?
                    WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND task_id = ? AND agent_id = ?
                    """,
                    (version, occurred_at, *request.scope.values()),
                )
                self._append_event(
                    connection,
                    request,
                    event_type="BUDGET_CANCELLED",
                    budget_version=version,
                    payload={"reason": request.input["reason"]},
                )
                response = self._snapshot(connection, request)
                self._record_operation(connection, request, response)
                connection.commit()
                return response
            except BaseException:
                connection.rollback()
                raise

    def _audit(self, request: StepBudgetRequest) -> dict[str, object]:
        with closing(self._connect()) as connection:
            self._budget_row(connection, request.scope)
            events = self._verify_event_chain(connection, request.scope)
        selected = [
            event
            for event in events
            if int(event["sequence"]) > int(request.input["after_sequence"])
        ][: int(request.input["limit"])]
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "runtime_version": RUNTIME_VERSION,
            "skill_name": SKILL_NAME,
            "operation": "audit",
            "request_sha256": request.digest,
            "decision": "READ_ONLY",
            "scope": request.scope.as_dict(),
            "events": copy.deepcopy(selected),
            "has_more": bool(selected and int(selected[-1]["sequence"]) < int(events[-1]["sequence"])),
            "replayed": False,
            "control_plane_execution_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "domain_runtime_evidence_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "customer_evidence_status": NOT_RUN,
            "external_evidence_status": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "side_effects_performed": False,
        }


__all__ = [
    "ACTIVE",
    "BLOCKED_RECONCILIATION",
    "BudgetScope",
    "CANCELLED",
    "COMPLEXITY_MULTIPLIER_BPS",
    "EXHAUSTED",
    "OPERATIONS",
    "PERMISSIONS",
    "REQUEST_SCHEMA_VERSION",
    "RESPONSE_SCHEMA_VERSION",
    "RUNTIME_VERSION",
    "SKILL_NAME",
    "STATE_SCHEMA_SHA256",
    "StepBudgetRequest",
    "StepBudgetStore",
    "authorization_scope_sha256",
    "validate_step_budget_request",
]
