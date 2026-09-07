"""Domain-specific autonomous QA test-plan generators.

The source package describes eleven materially different test domains.  This
module implements their portable, deterministic planning semantics without
pretending that a native framework, browser, database, load generator, scanner,
or chaos runner has executed.  Generated cases are therefore useful Test DSL
inputs, while native-source generation, materialization, and execution remain
explicit external gates.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ContractError, digest_json, require_exact_text, require_resource_id, require_text, strict_json


MAX_INPUT_ITEMS = 10_000
MAX_GENERATED_CASES = 5_000
PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})


def _exact_inputs(inputs: Mapping[str, Any], *fields: str) -> None:
    allowed = {"requirements", "_runtime_context", *fields}
    unknown = sorted(set(inputs).difference(allowed))
    if unknown:
        raise ContractError(f"generator input has unsupported fields: {unknown}")
    if "requirements" not in inputs:
        raise ContractError("generator input is missing requirements")
    context = inputs.get("_runtime_context")
    if context is None:
        return
    if not isinstance(context, Mapping) or any(type(key) is not str for key in context):
        raise ContractError("_runtime_context must be an exact string-keyed object")
    expected = {
        "tenant_id",
        "project_id",
        "actor_id",
        "request_id",
        "idempotency_key",
    }
    if set(context) != expected:
        raise ContractError("_runtime_context must contain the exact runtime-owned fields")
    for field in ("tenant_id", "project_id", "actor_id", "request_id"):
        value = context[field]
        if value is not None:
            require_resource_id(value, f"runtime.{field}")
    if context["idempotency_key"] is not None:
        require_text(context["idempotency_key"], "runtime.idempotency_key", maximum=200)


def _objects(inputs: Mapping[str, Any], field: str, *, required: bool = False) -> list[Mapping[str, Any]]:
    value = inputs.get(field)
    if value is None and not required:
        return []
    if not isinstance(value, list) or (required and not value):
        qualifier = "non-empty " if required else ""
        raise ContractError(f"{field} must be a {qualifier}array")
    if len(value) > MAX_INPUT_ITEMS or any(not isinstance(item, Mapping) for item in value):
        raise ContractError(f"{field} must contain at most {MAX_INPUT_ITEMS} objects")
    return list(value)


def _strings(value: Any, field: str, *, required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or (required and not value) or len(value) > MAX_INPUT_ITEMS:
        qualifier = "non-empty " if required else ""
        raise ContractError(f"{field} must be a {qualifier}bounded string array")
    result = [require_text(item, f"{field}[]", maximum=2048) for item in value]
    if len(set(result)) != len(result):
        raise ContractError(f"{field} may not contain duplicates")
    return result


def _bool(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ContractError(f"{field} must be boolean")
    return value


def _number(value: Any, field: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= float(value):
        raise ContractError(f"{field} must be a finite number >= {minimum}")
    result = float(value)
    if result != result or result in {float("inf"), float("-inf")}:
        raise ContractError(f"{field} must be finite")
    return result


def _requirements(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _objects(inputs, "requirements", required=True):
        requirement_id = require_resource_id(item.get("requirement_id"), "requirement_id")
        if requirement_id in seen:
            raise ContractError(f"duplicate requirement_id: {requirement_id}")
        seen.add(requirement_id)
        priority = require_text(item.get("priority", "P2"), "requirement.priority")
        if priority not in PRIORITIES:
            raise ContractError("requirement.priority is unsupported")
        required = _bool(item.get("required"), "requirement.required", default=True)
        criteria = _strings(item.get("acceptance_criteria", []), "acceptance_criteria")
        statement = require_exact_text(item.get("statement"), "requirement.statement", maximum=8192)
        title = require_text(item.get("title", requirement_id), "requirement.title", maximum=400)
        risk_tags = _strings(item.get("risk_tags", []), "requirement.risk_tags")
        normalized.append(
            {
                "requirement_id": requirement_id,
                "priority": priority,
                "required": required,
                "title": title,
                "statement": statement,
                "acceptance_criteria": criteria,
                "risk_tags": risk_tags,
            }
        )
    return normalized


def _case_id(domain: str, requirement_id: str, strategy: str) -> str:
    token = f"{domain}:{requirement_id}:{strategy}"
    suffix = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return require_resource_id(f"TC-{domain.upper().replace('_', '-')}-{suffix}", "test_case_id")


def _recipes(
    requirements: Sequence[Mapping[str, Any]],
    *,
    domain: str,
    recipes: Sequence[tuple[str, str, str, str, bool]],
) -> list[dict[str, Any]]:
    if len(requirements) * len(recipes) > MAX_GENERATED_CASES:
        raise ContractError("generated test plan exceeds the case limit")
    cases: list[dict[str, Any]] = []
    for requirement in requirements:
        requirement_id = str(requirement["requirement_id"])
        assertion = (
            str(requirement["acceptance_criteria"][0])
            if requirement["acceptance_criteria"]
            else str(requirement["statement"])
        )
        for strategy, action, oracle_kind, oracle_suffix, side_effect in recipes:
            test_case_id = _case_id(domain, requirement_id, strategy)
            cases.append(
                {
                    "test_case_id": test_case_id,
                    "title": f"{strategy}: {requirement['title']}",
                    "test_type": domain,
                    "priority": requirement["priority"],
                    "required": requirement["required"],
                    "requirement_refs": [requirement_id],
                    "risk_tags": list(requirement["risk_tags"]),
                    "preconditions": [],
                    "parameters": {"strategy": strategy, "domain": domain},
                    "steps": [
                        {
                            "step_id": f"step-{strategy}",
                            "action": action,
                            "input": {"requirement_id": requirement_id, "strategy": strategy},
                            "side_effect": side_effect,
                        }
                    ],
                    "oracles": [
                        {
                            "oracle_id": f"oracle-{strategy}",
                            "kind": oracle_kind,
                            "assertion": f"{assertion}; {oracle_suffix}",
                        }
                    ],
                    "evidence_requirements": ["structured-result", "native-runner-raw-output"],
                    "cleanup": ["restore-isolated-fixture"] if side_effect else [],
                    "executor": {"binding_status": "UNBOUND", "execution_status": "NOT_RUN"},
                    "materialization": {"status": "NOT_RUN"},
                }
            )
    return cases


def _result(
    *,
    code: str,
    cases: Sequence[Mapping[str, Any]],
    outputs: Mapping[str, Any],
    blockers: Sequence[str],
) -> Mapping[str, Any]:
    payload = {
        "test_cases": list(cases),
        "requirement_case_matrix": [
            {
                "requirement_id": case["requirement_refs"][0],
                "test_case_id": case["test_case_id"],
                "strategy": case["parameters"]["strategy"],
            }
            for case in cases
        ],
        **dict(outputs),
        "blockers": list(blockers),
        "dsl_generation": "LOCAL_EXECUTED",
        "native_source_generation": "NOT_RUN",
        "materialization": "NOT_RUN",
        "runner_execution": "NOT_RUN",
        "external_evidence": "NOT_RUN",
    }
    payload["generator_digest"] = digest_json(payload)
    strict_json(payload, "generator output")
    return {
        "state": "PARTIAL",
        "code": code,
        "outputs": payload,
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


def generate_functional_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Generate rule, boundary, state, permission, concurrency, and recovery cases."""

    _exact_inputs(
        inputs,
        "business_rules",
        "state_models",
        "roles",
        "operations",
        "boundaries",
    )
    requirements = _requirements(inputs)
    business_rules = _objects(inputs, "business_rules")
    state_models = _objects(inputs, "state_models")
    roles = _objects(inputs, "roles")
    operations = _objects(inputs, "operations")
    boundaries = _objects(inputs, "boundaries")

    normalized_rules = [
        {
            "rule_id": require_resource_id(rule.get("rule_id"), "business_rules[].rule_id"),
            "assertion": require_exact_text(rule.get("assertion"), "business_rules[].assertion", maximum=4096),
            "requirement_refs": _strings(rule.get("requirement_refs", []), "business_rules[].requirement_refs"),
        }
        for rule in business_rules
    ]
    boundary_table = [
        {
            "field_id": require_resource_id(item.get("field_id"), "boundaries[].field_id"),
            "data_type": require_text(item.get("data_type"), "boundaries[].data_type"),
            "minimum": strict_json(item.get("minimum"), "boundaries[].minimum") if "minimum" in item else None,
            "maximum": strict_json(item.get("maximum"), "boundaries[].maximum") if "maximum" in item else None,
            "nullable": _bool(item.get("nullable"), "boundaries[].nullable"),
            "enum": _strings(item.get("enum", []), "boundaries[].enum"),
        }
        for item in boundaries
    ]
    transitions: list[dict[str, Any]] = []
    for model in state_models:
        model_id = require_resource_id(model.get("state_model_id"), "state_models[].state_model_id")
        states = _strings(model.get("states"), "state_models[].states", required=True)
        for transition in _objects(model, "transitions", required=True):
            source = require_resource_id(transition.get("from"), "transition.from")
            target = require_resource_id(transition.get("to"), "transition.to")
            if source not in states or target not in states:
                raise ContractError("state transition references an undeclared state")
            transitions.append(
                {
                    "state_model_id": model_id,
                    "from": source,
                    "to": target,
                    "event": require_resource_id(transition.get("event"), "transition.event"),
                    "allowed": _bool(transition.get("allowed"), "transition.allowed", default=True),
                }
            )
    permission_pairs: list[dict[str, Any]] = []
    for role in roles:
        role_id = require_resource_id(role.get("role_id"), "roles[].role_id")
        for action in _strings(role.get("allowed_actions", []), "roles[].allowed_actions"):
            permission_pairs.append({"role_id": role_id, "action": action, "expected": "ALLOW"})
        for action in _strings(role.get("denied_actions", []), "roles[].denied_actions"):
            permission_pairs.append({"role_id": role_id, "action": action, "expected": "DENY_NO_SIDE_EFFECT"})
    operation_models = [
        {
            "operation_id": require_resource_id(item.get("operation_id"), "operations[].operation_id"),
            "side_effect": _bool(item.get("side_effect"), "operations[].side_effect"),
            "idempotency_required": _bool(item.get("idempotency_required"), "operations[].idempotency_required"),
            "concurrency_required": _bool(item.get("concurrency_required"), "operations[].concurrency_required"),
        }
        for item in operations
    ]
    recipes = (
        ("happy-path", "invoke-business-rule", "value", "the declared result and side effects match", True),
        ("negative", "invoke-invalid-business-input", "state", "the declared error is returned with no side effects", False),
        ("boundary", "exercise-declared-boundary", "value", "range, enum, null, and time rules are preserved", False),
        ("legal-state-transition", "transition-state", "state", "the legal transition commits exactly once", True),
        ("illegal-state-transition", "attempt-illegal-transition", "state", "state and data remain unchanged", True),
        ("permission-allow-deny", "invoke-as-role-and-tenant", "security", "allow and deny outcomes preserve tenant ownership", True),
        ("idempotent-retry", "repeat-side-effect-with-key", "state", "retries create no duplicate business effect", True),
        ("concurrent-invocation", "invoke-concurrently", "invariant", "the declared concurrency invariant remains true", True),
        ("error-recovery", "retry-after-dependency-failure", "state", "recovery is bounded and leaves no half-complete state", True),
    )
    cases = _recipes(requirements, domain="functional", recipes=recipes)
    blockers = [
        name
        for name, value in (
            ("BUSINESS_RULES_REQUIRED", normalized_rules),
            ("BOUNDARY_MODEL_REQUIRED", boundary_table),
            ("STATE_MODEL_REQUIRED", transitions),
            ("ROLE_TENANT_MODEL_REQUIRED", permission_pairs),
            ("SIDE_EFFECT_OPERATION_MODEL_REQUIRED", operation_models),
        )
        if not value
    ]
    return _result(
        code="FUNCTIONAL_TEST_MODEL_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "business_rules": normalized_rules,
            "boundary_table": boundary_table,
            "state_transition_coverage": transitions,
            "permission_pairs": permission_pairs,
            "side_effect_operations": operation_models,
            "fixtures": {"mutable_data_shared": False, "clock_controlled": True, "randomness_seeded": True},
        },
    )


def plan_api_contract_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Parse typed API operations and derive compatibility and behavioral cases."""

    _exact_inputs(inputs, "api_operations", "consumer_contracts")
    requirements = _requirements(inputs)
    operations: list[dict[str, Any]] = []
    breaking: list[dict[str, Any]] = []
    for item in _objects(inputs, "api_operations"):
        operation_id = require_resource_id(item.get("operation_id"), "api_operations[].operation_id")
        protocol = require_text(item.get("protocol"), "api_operations[].protocol").lower()
        if protocol not in {"rest", "graphql", "grpc", "asyncapi"}:
            raise ContractError("api operation protocol is unsupported")
        current_fields = _strings(item.get("response_fields", []), "api_operations[].response_fields")
        previous_fields = _strings(item.get("previous_response_fields", []), "api_operations[].previous_response_fields")
        required_fields = _strings(item.get("required_request_fields", []), "api_operations[].required_request_fields")
        previous_required = _strings(item.get("previous_required_request_fields", []), "api_operations[].previous_required_request_fields")
        removed = sorted(set(previous_fields) - set(current_fields))
        tightened = sorted(set(required_fields) - set(previous_required))
        for field in removed:
            breaking.append({"operation_id": operation_id, "kind": "RESPONSE_FIELD_REMOVED", "field": field})
        for field in tightened:
            breaking.append({"operation_id": operation_id, "kind": "REQUEST_FIELD_NEWLY_REQUIRED", "field": field})
        operations.append(
            {
                "operation_id": operation_id,
                "protocol": protocol,
                "request_fields": _strings(item.get("request_fields", []), "api_operations[].request_fields"),
                "required_request_fields": required_fields,
                "response_fields": current_fields,
                "content_types": _strings(item.get("content_types", []), "api_operations[].content_types"),
                "security_schemes": _strings(item.get("security_schemes", []), "api_operations[].security_schemes"),
                "side_effects": _strings(item.get("side_effects", []), "api_operations[].side_effects"),
            }
        )
    consumers = [
        {
            "consumer_id": require_resource_id(item.get("consumer_id"), "consumer_contracts[].consumer_id"),
            "version": require_text(item.get("version"), "consumer_contracts[].version"),
            "operation_refs": _strings(item.get("operation_refs"), "consumer_contracts[].operation_refs", required=True),
        }
        for item in _objects(inputs, "consumer_contracts")
    ]
    recipes = (
        ("schema-valid", "send-schema-valid-request", "value", "response schema and declared behavior match", True),
        ("schema-invalid", "send-schema-invalid-request", "state", "validation error is exact and has no side effect", False),
        ("missing-field", "omit-required-field", "state", "required-field semantics are enforced", False),
        ("extra-field", "send-unknown-field", "state", "unknown-field policy is explicit", False),
        ("boundary", "send-extreme-value", "value", "declared numeric, length, null, and time bounds hold", False),
        ("content-type", "negotiate-content-type", "value", "content negotiation is compatible", False),
        ("authentication", "invoke-with-invalid-identity", "security", "authentication fails without detail leakage", False),
        ("authorization", "invoke-with-disallowed-role", "security", "authorization denies with no cross-tenant disclosure", True),
        ("tenant-isolation", "invoke-cross-tenant", "security", "cross-tenant access and side effects are denied", True),
        ("rate-limit", "exceed-declared-rate", "timing", "rate limit and recovery headers follow contract", False),
        ("idempotency", "repeat-idempotency-key", "state", "response and backend side effects are idempotent", True),
        ("pagination", "traverse-pagination", "data", "items are neither duplicated nor omitted", False),
        ("backend-side-effect", "observe-backend-side-effect", "event", "data, event, and audit effects match the operation", True),
    )
    cases = _recipes(requirements, domain="api", recipes=recipes)
    blockers = [] if operations else ["API_SCHEMA_OR_OPERATION_MODEL_REQUIRED"]
    return _result(
        code="API_CONTRACT_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "api_operations": operations,
            "breaking_change_findings": breaking,
            "consumer_impact": consumers,
            "provider_consumer_execution": "NOT_RUN",
            "har_trace_capture": "NOT_RUN",
            "redaction_required": True,
        },
    )


def plan_database_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Model constraints, transactions, queries, migrations, and retention checks."""

    _exact_inputs(inputs, "tables", "migrations")
    requirements = _requirements(inputs)
    tables: list[dict[str, Any]] = []
    for table in _objects(inputs, "tables"):
        table_id = require_resource_id(table.get("table_id"), "tables[].table_id")
        columns = []
        for column in _objects(table, "columns", required=True):
            columns.append(
                {
                    "column_id": require_resource_id(column.get("column_id"), "columns[].column_id"),
                    "data_type": require_text(column.get("data_type"), "columns[].data_type"),
                    "nullable": _bool(column.get("nullable"), "columns[].nullable", default=True),
                    "primary_key": _bool(column.get("primary_key"), "columns[].primary_key"),
                    "unique": _bool(column.get("unique"), "columns[].unique"),
                    "default_declared": "default" in column,
                    "checks": _strings(column.get("checks", []), "columns[].checks"),
                }
            )
        tables.append(
            {
                "table_id": table_id,
                "columns": columns,
                "foreign_keys": _objects(table, "foreign_keys"),
                "business_invariants": _strings(table.get("business_invariants", []), "tables[].business_invariants"),
            }
        )
    migrations = [
        {
            "migration_id": require_resource_id(item.get("migration_id"), "migrations[].migration_id"),
            "source_version": require_text(item.get("source_version"), "migrations[].source_version"),
            "target_version": require_text(item.get("target_version"), "migrations[].target_version"),
            "idempotency_strategy": require_text(item.get("idempotency_strategy"), "migrations[].idempotency_strategy"),
            "rollback_declared": _bool(item.get("rollback_declared"), "migrations[].rollback_declared"),
        }
        for item in _objects(inputs, "migrations")
    ]
    recipes = (
        ("primary-key", "violate-primary-key", "data", "primary-key uniqueness and error semantics hold", True),
        ("foreign-key", "violate-foreign-key", "data", "referential integrity is preserved", True),
        ("not-null-check-default", "exercise-column-constraints", "data", "null, check, and default semantics match the schema", True),
        ("transaction-atomicity", "interrupt-transaction", "invariant", "all writes commit or all roll back", True),
        ("isolation-concurrency", "interleave-concurrent-transactions", "invariant", "the declared isolation invariant holds", True),
        ("deadlock-retry", "force-deadlock-order", "state", "deadlock handling is bounded and idempotent", True),
        ("query-plan-index", "inspect-query-plan", "resource", "correctness holds and index regression is detectable", False),
        ("migration-interrupt-resume", "interrupt-and-resume-migration", "data", "no undeclared half-complete state remains", True),
        ("migration-rollback", "rollback-migration", "data", "row detail, checksums, invariants, and references reconcile", True),
        ("retention-cleanup", "exercise-retention-policy", "state", "archive, deletion, and audit policy remain consistent", True),
    )
    cases = _recipes(requirements, domain="database", recipes=recipes)
    blockers = []
    if not tables:
        blockers.append("DATABASE_SCHEMA_REQUIRED")
    if not migrations:
        blockers.append("MIGRATION_MODEL_REQUIRED")
    return _result(
        code="DATABASE_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "schema_model": tables,
            "migration_model": migrations,
            "reconciliation_dimensions": ["row-detail", "checksum", "business-invariant", "referential-integrity"],
            "query_plan_capture": "NOT_RUN",
            "database_execution": "NOT_RUN",
            "production_writes_authorized": False,
        },
    )


def plan_message_workflow_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Model message delivery, workflow compensation, and scheduler edge cases."""

    _exact_inputs(inputs, "messages", "workflows", "schedules")
    requirements = _requirements(inputs)
    messages = [
        {
            "message_id": require_resource_id(item.get("message_id"), "messages[].message_id"),
            "destination": require_resource_id(item.get("destination"), "messages[].destination"),
            "schema_version": require_text(item.get("schema_version"), "messages[].schema_version"),
            "delivery_semantics": require_text(item.get("delivery_semantics"), "messages[].delivery_semantics"),
            "ordering_key": require_text(item.get("ordering_key"), "messages[].ordering_key") if item.get("ordering_key") is not None else None,
            "deduplication_window_seconds": _number(item.get("deduplication_window_seconds", 0), "messages[].deduplication_window_seconds"),
            "retry_limit": int(_number(item.get("retry_limit", 0), "messages[].retry_limit")),
            "dead_letter_declared": _bool(item.get("dead_letter_declared"), "messages[].dead_letter_declared"),
        }
        for item in _objects(inputs, "messages")
    ]
    workflows: list[dict[str, Any]] = []
    for workflow in _objects(inputs, "workflows"):
        workflow_id = require_resource_id(workflow.get("workflow_id"), "workflows[].workflow_id")
        steps = []
        for step in _objects(workflow, "steps", required=True):
            steps.append(
                {
                    "step_id": require_resource_id(step.get("step_id"), "workflow.steps[].step_id"),
                    "timeout_seconds": _number(step.get("timeout_seconds"), "workflow.steps[].timeout_seconds", minimum=0.001),
                    "compensation": require_resource_id(step.get("compensation"), "workflow.steps[].compensation"),
                    "compensation_idempotent": _bool(step.get("compensation_idempotent"), "workflow.steps[].compensation_idempotent"),
                }
            )
        workflows.append({"workflow_id": workflow_id, "steps": steps})
    schedules = [
        {
            "schedule_id": require_resource_id(item.get("schedule_id"), "schedules[].schedule_id"),
            "timezone": require_text(item.get("timezone"), "schedules[].timezone"),
            "cron": require_text(item.get("cron"), "schedules[].cron"),
            "dst_policy": require_text(item.get("dst_policy"), "schedules[].dst_policy"),
        }
        for item in _objects(inputs, "schedules")
    ]
    recipes = (
        ("schema-version", "publish-schema-variant", "event", "schema compatibility and unknown-field policy hold", True),
        ("duplicate", "deliver-message-twice", "invariant", "business side effects are deduplicated", True),
        ("out-of-order", "reorder-messages", "state", "ordering policy and convergence are explicit", True),
        ("delay-loss", "delay-or-withhold-message", "timing", "timeout and missing-message recovery are bounded", True),
        ("poison-message", "deliver-poison-message", "state", "the partition progresses and poison input is quarantined", True),
        ("retry-backoff", "fail-consumer-repeatedly", "timing", "retry limit and backoff are enforced", True),
        ("dead-letter-replay", "dead-letter-and-replay", "event", "replay is isolated, correlated, and idempotent", True),
        ("saga-compensation", "fail-each-workflow-step", "state", "each compensation is complete and idempotent", True),
        ("scheduler-dst", "trigger-schedule-at-time-boundary", "timing", "timezone, DST, duplicate, and missed trigger policy hold", True),
    )
    cases = _recipes(requirements, domain="message", recipes=recipes)
    blockers = []
    if not messages:
        blockers.append("MESSAGE_SCHEMA_AND_DELIVERY_MODEL_REQUIRED")
    if not workflows:
        blockers.append("WORKFLOW_COMPENSATION_MODEL_REQUIRED")
    return _result(
        code="MESSAGE_WORKFLOW_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "message_models": messages,
            "workflow_models": workflows,
            "schedule_models": schedules,
            "time_domains_separated": True,
            "broker_execution": "NOT_RUN",
            "workflow_execution": "NOT_RUN",
        },
    )


def plan_ui_e2e_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Model observable user journeys without claiming browser/device execution."""

    _exact_inputs(inputs, "journeys", "support_matrix")
    requirements = _requirements(inputs)
    journeys: list[dict[str, Any]] = []
    for journey in _objects(inputs, "journeys"):
        journey_id = require_resource_id(journey.get("journey_id"), "journeys[].journey_id")
        steps: list[dict[str, Any]] = []
        for step in _objects(journey, "steps", required=True):
            locator = require_text(step.get("locator"), "journey.steps[].locator", maximum=1024)
            if locator.startswith("/") or "xpath=" in locator.casefold():
                raise ContractError("absolute XPath is not a permitted default locator")
            wait_for = require_text(step.get("wait_for"), "journey.steps[].wait_for")
            if "sleep" in wait_for.casefold():
                raise ContractError("fixed sleep is not an observable wait")
            steps.append(
                {
                    "step_id": require_resource_id(step.get("step_id"), "journey.steps[].step_id"),
                    "action": require_resource_id(step.get("action"), "journey.steps[].action"),
                    "locator": locator,
                    "wait_for": wait_for,
                    "observable": require_exact_text(step.get("observable"), "journey.steps[].observable", maximum=2048),
                    "backend_effect": require_exact_text(step.get("backend_effect"), "journey.steps[].backend_effect", maximum=2048),
                }
            )
        journeys.append(
            {
                "journey_id": journey_id,
                "role": require_resource_id(journey.get("role"), "journeys[].role"),
                "tenant": require_resource_id(journey.get("tenant"), "journeys[].tenant"),
                "steps": steps,
                "isolated_test_data": _bool(journey.get("isolated_test_data"), "journeys[].isolated_test_data"),
            }
        )
    support = [
        {
            "browser": require_text(item.get("browser"), "support_matrix[].browser"),
            "version": require_text(item.get("version"), "support_matrix[].version"),
            "device": require_text(item.get("device"), "support_matrix[].device"),
            "os": require_text(item.get("os"), "support_matrix[].os"),
        }
        for item in _objects(inputs, "support_matrix")
    ]
    recipes = (
        ("critical-journey", "execute-observable-journey", "state", "each step and backend effect are observed", True),
        ("forms-navigation", "exercise-form-navigation-history", "state", "validation, refresh, and back navigation preserve state", True),
        ("upload-download", "exercise-file-transfer", "data", "content, authorization, and cleanup are verified", True),
        ("permission", "execute-journey-as-denied-role", "security", "the UI and backend both deny the action", True),
        ("error-state", "inject-service-error", "state", "the user receives an actionable recoverable error", True),
        ("weak-network", "inject-network-degradation", "timing", "timeouts and retry UX do not duplicate effects", True),
        ("session-expiry", "expire-session-mid-journey", "security", "identity is re-established without cross-user state", True),
        ("console-network", "observe-console-and-network", "invariant", "no unexplained error, failed request, or redirect remains", False),
    )
    cases = _recipes(requirements, domain="ui_e2e", recipes=recipes)
    blockers = []
    if not journeys:
        blockers.append("USER_JOURNEYS_REQUIRED")
    if not support:
        blockers.append("BROWSER_DEVICE_MATRIX_REQUIRED")
    return _result(
        code="UI_E2E_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "journeys": journeys,
            "support_matrix": support,
            "locator_policy": "ACCESSIBLE_ROLE_LABEL_OR_STABLE_TEST_ID",
            "browser_device_execution": "NOT_RUN",
            "screenshot_video_dom_console_network_trace": "NOT_RUN",
        },
    )


def plan_visual_responsive_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Plan fixed-environment visual capture and governed baseline comparison."""

    _exact_inputs(inputs, "visual_targets", "baselines")
    requirements = _requirements(inputs)
    targets = [
        {
            "target_id": require_resource_id(item.get("target_id"), "visual_targets[].target_id"),
            "viewports": _strings(item.get("viewports"), "visual_targets[].viewports", required=True),
            "themes": _strings(item.get("themes"), "visual_targets[].themes", required=True),
            "locales": _strings(item.get("locales"), "visual_targets[].locales", required=True),
            "content_lengths": _strings(item.get("content_lengths", []), "visual_targets[].content_lengths"),
            "semantic_masks": _strings(item.get("semantic_masks", []), "visual_targets[].semantic_masks"),
        }
        for item in _objects(inputs, "visual_targets")
    ]
    baselines = []
    for item in _objects(inputs, "baselines"):
        digest = require_text(item.get("sha256"), "baselines[].sha256", maximum=80)
        if not (len(digest.removeprefix("sha256:")) == 64 and all(c in "0123456789abcdef" for c in digest.removeprefix("sha256:"))):
            raise ContractError("visual baseline sha256 is invalid")
        baselines.append(
            {
                "baseline_id": require_resource_id(item.get("baseline_id"), "baselines[].baseline_id"),
                "sha256": "sha256:" + digest.removeprefix("sha256:"),
                "commit": require_text(item.get("commit"), "baselines[].commit"),
                "browser_image": require_text(item.get("browser_image"), "baselines[].browser_image"),
                "font_manifest": require_text(item.get("font_manifest"), "baselines[].font_manifest"),
                "approval_receipt": "NOT_RUN",
            }
        )
    recipes = (
        ("viewport-theme-locale", "capture-visual-matrix", "visual", "the declared visual matrix matches its governed baseline", False),
        ("pixel-diff", "compare-pixels", "visual", "local differences remain within component-specific rules", False),
        ("layout-semantic-diff", "compare-layout-semantics", "visual", "geometry and interaction semantics are preserved", False),
        ("overflow-overlap", "inspect-overflow-overlap", "visual", "text remains readable and controls remain clickable", False),
        ("scroll-z-index", "inspect-scroll-and-layering", "visual", "horizontal scroll and layer occlusion follow design", False),
        ("baseline-review", "request-baseline-review", "visual", "baseline mutation requires an authorized design change", True),
    )
    cases = _recipes(requirements, domain="visual", recipes=recipes)
    blockers = []
    if not targets:
        blockers.append("VISUAL_MATRIX_REQUIRED")
    if not baselines:
        blockers.append("DIGEST_BOUND_BASELINE_REQUIRED")
    return _result(
        code="VISUAL_RESPONSIVE_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "visual_targets": targets,
            "baselines": baselines,
            "environment_controls": ["font", "timezone", "animation", "random-data", "browser-version"],
            "baseline_auto_accept": False,
            "capture_and_diff": "NOT_RUN",
            "baseline_mutation": "NOT_RUN",
        },
    )


def plan_accessibility_compatibility_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Combine rule scans, semantic journeys, and real-engine compatibility plans."""

    _exact_inputs(inputs, "accessibility_targets", "compatibility_matrix")
    requirements = _requirements(inputs)
    targets = [
        {
            "target_id": require_resource_id(item.get("target_id"), "accessibility_targets[].target_id"),
            "roles": _strings(item.get("roles", []), "accessibility_targets[].roles"),
            "keyboard_path": _strings(item.get("keyboard_path"), "accessibility_targets[].keyboard_path", required=True),
            "dynamic_updates": _strings(item.get("dynamic_updates", []), "accessibility_targets[].dynamic_updates"),
            "components": _strings(item.get("components", []), "accessibility_targets[].components"),
        }
        for item in _objects(inputs, "accessibility_targets")
    ]
    support = [
        {
            "browser": require_text(item.get("browser"), "compatibility_matrix[].browser"),
            "engine": require_text(item.get("engine"), "compatibility_matrix[].engine"),
            "device": require_text(item.get("device"), "compatibility_matrix[].device"),
            "os": require_text(item.get("os"), "compatibility_matrix[].os"),
            "fallback": require_exact_text(item.get("fallback"), "compatibility_matrix[].fallback", maximum=2048),
        }
        for item in _objects(inputs, "compatibility_matrix")
    ]
    recipes = (
        ("structure-name-role-state", "scan-accessibility-semantics", "accessibility", "structure, accessible name, role, and state are correct", False),
        ("keyboard-focus", "execute-keyboard-only-journey", "accessibility", "focus order, visibility, trapping, and restoration are correct", False),
        ("form-errors", "exercise-form-and-error-semantics", "accessibility", "labels, associations, and error announcements are usable", False),
        ("dialogs-menus-tables", "exercise-composite-widget-semantics", "accessibility", "interaction and semantic contracts remain complete", False),
        ("contrast", "measure-contrast", "accessibility", "declared contrast threshold is met", False),
        ("dynamic-update", "observe-dynamic-update", "accessibility", "state changes are announced without focus loss", False),
        ("real-engine-compatibility", "probe-browser-device-capability", "state", "unsupported capability has an explicit usable fallback", False),
    )
    cases = _recipes(requirements, domain="accessibility", recipes=recipes)
    blockers = []
    if not targets:
        blockers.append("ACCESSIBILITY_JOURNEY_MODEL_REQUIRED")
    if not support:
        blockers.append("REAL_ENGINE_SUPPORT_MATRIX_REQUIRED")
    return _result(
        code="ACCESSIBILITY_COMPATIBILITY_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "accessibility_targets": targets,
            "compatibility_matrix": support,
            "automated_scan_is_sufficient": False,
            "scanner_execution": "NOT_RUN",
            "browser_device_execution": "NOT_RUN",
        },
    )


def plan_performance_baseline_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create calibrated workload/SLO plans and same-environment comparison rules."""

    _exact_inputs(inputs, "performance_scenarios", "slo_budgets", "environment")
    requirements = _requirements(inputs)
    scenarios = [
        {
            "scenario_id": require_resource_id(item.get("scenario_id"), "performance_scenarios[].scenario_id"),
            "arrival_rate_per_second": _number(item.get("arrival_rate_per_second"), "performance_scenarios[].arrival_rate_per_second", minimum=0.001),
            "concurrency": int(_number(item.get("concurrency"), "performance_scenarios[].concurrency", minimum=1)),
            "think_time_seconds": _number(item.get("think_time_seconds", 0), "performance_scenarios[].think_time_seconds"),
            "data_scale": require_text(item.get("data_scale"), "performance_scenarios[].data_scale"),
            "warmup_seconds": _number(item.get("warmup_seconds"), "performance_scenarios[].warmup_seconds"),
            "steady_state_seconds": _number(item.get("steady_state_seconds"), "performance_scenarios[].steady_state_seconds", minimum=0.001),
        }
        for item in _objects(inputs, "performance_scenarios")
    ]
    budgets = [
        {
            "metric": require_resource_id(item.get("metric"), "slo_budgets[].metric"),
            "percentile": require_text(item.get("percentile"), "slo_budgets[].percentile"),
            "maximum": _number(item.get("maximum"), "slo_budgets[].maximum"),
            "unit": require_text(item.get("unit"), "slo_budgets[].unit"),
            "regression_percent": _number(item.get("regression_percent"), "slo_budgets[].regression_percent"),
        }
        for item in _objects(inputs, "slo_budgets")
    ]
    environment = inputs.get("environment")
    normalized_environment: dict[str, Any] | None = None
    if environment is not None:
        if not isinstance(environment, Mapping):
            raise ContractError("environment must be an object")
        normalized_environment = {
            "environment_id": require_resource_id(environment.get("environment_id"), "environment.environment_id"),
            "image_digest": require_text(environment.get("image_digest"), "environment.image_digest"),
            "data_digest": require_text(environment.get("data_digest"), "environment.data_digest"),
            "load_generator_capacity_verified": False,
        }
    recipes = (
        ("calibration", "calibrate-environment-and-generator", "resource", "noise, cache state, and generator saturation are measured", False),
        ("warmup", "warm-performance-scenario", "resource", "warmup reaches declared stable conditions", False),
        ("steady-state", "run-steady-state-workload", "timing", "SLO holds for the full steady-state interval", True),
        ("tail-latency", "measure-latency-distribution", "timing", "p50, p95, and p99 include error requests", False),
        ("throughput-error", "measure-throughput-and-errors", "resource", "throughput and error rate remain within budget", False),
        ("resource-correlation", "correlate-client-server-traces", "resource", "CPU, memory, GC, database, cache, network, and dependencies explain the result", False),
        ("same-environment-diff", "compare-approved-baseline", "differential", "only identical environment and workload identities are compared", False),
    )
    cases = _recipes(requirements, domain="performance", recipes=recipes)
    blockers = []
    if not scenarios:
        blockers.append("BUSINESS_WORKLOAD_MODEL_REQUIRED")
    if not budgets:
        blockers.append("SLO_OR_PROVISIONAL_BUDGET_REQUIRED")
    if normalized_environment is None:
        blockers.append("DIGEST_BOUND_ENVIRONMENT_REQUIRED")
    return _result(
        code="PERFORMANCE_BASELINE_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "performance_scenarios": scenarios,
            "slo_budgets": budgets,
            "environment": normalized_environment,
            "required_metrics": ["p50", "p95", "p99", "throughput", "error-rate", "cpu", "memory", "network"],
            "load_execution": "NOT_RUN",
            "metrics_collection": "NOT_RUN",
        },
    )


def plan_load_stress_spike_soak_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Plan distinct load, stress, spike, soak, capacity, and recovery phases."""

    _exact_inputs(inputs, "workload_phases", "capacity_profiles")
    requirements = _requirements(inputs)
    phases: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for item in _objects(inputs, "workload_phases"):
        phase_id = require_resource_id(item.get("phase_id"), "workload_phases[].phase_id")
        phase_type = require_text(item.get("phase_type"), "workload_phases[].phase_type").lower()
        if phase_type not in {"load", "stress", "spike", "soak", "capacity", "recovery"}:
            raise ContractError("workload phase type is unsupported")
        duration = _number(item.get("duration_seconds"), "workload_phases[].duration_seconds", minimum=0.001)
        curve = _strings(item.get("arrival_curve"), "workload_phases[].arrival_curve", required=True)
        stop_conditions = _strings(item.get("stop_conditions"), "workload_phases[].stop_conditions", required=True)
        if phase_type == "soak" and _bool(item.get("parallel_time_compression"), "workload_phases[].parallel_time_compression"):
            raise ContractError("soak wall-clock duration may not be compressed by parallelism")
        seen_types.add(phase_type)
        phases.append(
            {
                "phase_id": phase_id,
                "phase_type": phase_type,
                "duration_seconds": duration,
                "arrival_curve": curve,
                "stop_conditions": stop_conditions,
                "resource_profile": require_text(item.get("resource_profile"), "workload_phases[].resource_profile"),
                "parallel_time_compression": False,
            }
        )
    capacity = [
        {
            "profile_id": require_resource_id(item.get("profile_id"), "capacity_profiles[].profile_id"),
            "replicas": int(_number(item.get("replicas"), "capacity_profiles[].replicas", minimum=1)),
            "cpu": require_text(item.get("cpu"), "capacity_profiles[].cpu"),
            "memory": require_text(item.get("memory"), "capacity_profiles[].memory"),
            "cost_basis": require_text(item.get("cost_basis"), "capacity_profiles[].cost_basis"),
        }
        for item in _objects(inputs, "capacity_profiles")
    ]
    recipes = (
        ("load", "run-target-load", "timing", "target SLO and data integrity hold", True),
        ("stress", "increase-load-to-first-budget-break", "resource", "the first saturated resource and break point are identified", True),
        ("spike", "apply-and-remove-traffic-spike", "timing", "queueing, throttling, scaling, and recovery are bounded", True),
        ("soak", "run-full-duration-soak", "resource", "memory, handle, connection, latency, and backlog trends remain bounded", True),
        ("capacity", "compare-capacity-profiles", "differential", "stable throughput, scale efficiency, and cost are measured", True),
        ("recovery", "stop-load-and-observe-recovery", "state", "health and business data return to the declared invariant", True),
    )
    cases = _recipes(requirements, domain="load", recipes=recipes)
    missing = sorted({"load", "stress", "spike", "soak", "capacity", "recovery"} - seen_types)
    blockers = [f"WORKLOAD_PHASE_REQUIRED:{item}" for item in missing]
    if not capacity:
        blockers.append("CAPACITY_PROFILE_REQUIRED")
    return _result(
        code="LOAD_STRESS_SPIKE_SOAK_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "workload_phases": phases,
            "capacity_profiles": capacity,
            "authorized_isolated_environment_required": True,
            "load_runner_execution": "NOT_RUN",
            "metrics_collection": "NOT_RUN",
        },
    )


def plan_security_abuse_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Derive authorized threat and abuse cases without running active attacks."""

    _exact_inputs(inputs, "trust_boundaries", "threats", "authorization_pairs")
    requirements = _requirements(inputs)
    boundaries = [
        {
            "boundary_id": require_resource_id(item.get("boundary_id"), "trust_boundaries[].boundary_id"),
            "source_zone": require_resource_id(item.get("source_zone"), "trust_boundaries[].source_zone"),
            "target_zone": require_resource_id(item.get("target_zone"), "trust_boundaries[].target_zone"),
            "data_classes": _strings(item.get("data_classes"), "trust_boundaries[].data_classes", required=True),
            "required_controls": _strings(item.get("required_controls"), "trust_boundaries[].required_controls", required=True),
        }
        for item in _objects(inputs, "trust_boundaries")
    ]
    threats = [
        {
            "threat_id": require_resource_id(item.get("threat_id"), "threats[].threat_id"),
            "entrypoint": require_resource_id(item.get("entrypoint"), "threats[].entrypoint"),
            "category": require_resource_id(item.get("category"), "threats[].category"),
            "authorized_scope": _bool(item.get("authorized_scope"), "threats[].authorized_scope"),
            "expected_control": require_exact_text(item.get("expected_control"), "threats[].expected_control", maximum=4096),
        }
        for item in _objects(inputs, "threats")
    ]
    if any(not threat["authorized_scope"] for threat in threats):
        raise ContractError("out-of-scope active security scenarios may not be planned")
    role_pairs = [
        {
            "resource_id": require_resource_id(item.get("resource_id"), "authorization_pairs[].resource_id"),
            "owner_tenant": require_resource_id(item.get("owner_tenant"), "authorization_pairs[].owner_tenant"),
            "allowed_role": require_resource_id(item.get("allowed_role"), "authorization_pairs[].allowed_role"),
            "denied_role": require_resource_id(item.get("denied_role"), "authorization_pairs[].denied_role"),
            "foreign_tenant": require_resource_id(item.get("foreign_tenant"), "authorization_pairs[].foreign_tenant"),
        }
        for item in _objects(inputs, "authorization_pairs")
    ]
    recipes = (
        ("authentication-session", "simulate-authentication-and-session-abuse", "security", "bypass fails and session lifecycle is bounded", False),
        ("authorization-role", "simulate-horizontal-and-vertical-access", "security", "allow and deny outcomes match resource ownership", True),
        ("tenant-isolation", "simulate-cross-tenant-access", "security", "no data, cache, error, or side effect crosses tenants", True),
        ("input-injection", "prepare-inert-injection-corpus", "security", "inputs are rejected or safely interpreted", False),
        ("upload-deserialization-path-ssrf", "prepare-inert-parser-abuse-corpus", "security", "parser, path, and network boundaries remain closed", False),
        ("resource-abuse", "plan-rate-and-resource-abuse", "resource", "limits, recovery, and audit remain effective", True),
        ("secret-and-data-leakage", "inspect-redacted-observations", "security", "secrets and personal data do not appear in errors, logs, caches, or clients", False),
        ("scanner-correlation", "normalize-security-findings", "differential", "static, dependency, dynamic, and business findings require reproduction", False),
        ("risk-control-evasion", "plan-risk-control-evasion", "security", "rate, challenge, fraud, and audit controls recover without bypass", True),
    )
    cases = _recipes(requirements, domain="security", recipes=recipes)
    blockers = []
    if not boundaries:
        blockers.append("TRUST_BOUNDARY_AND_DATA_FLOW_REQUIRED")
    if not threats:
        blockers.append("AUTHORIZED_THREAT_MODEL_REQUIRED")
    if not role_pairs:
        blockers.append("ALLOW_DENY_TENANT_PAIRS_REQUIRED")
    return _result(
        code="SECURITY_ABUSE_TEST_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "trust_boundaries": boundaries,
            "threat_scenarios": threats,
            "authorization_pairs": role_pairs,
            "active_attack_execution": "NOT_RUN",
            "sast_sca_dast_execution": "NOT_RUN",
            "plaintext_secret_or_personal_data_retained": False,
        },
    )


def plan_resilience_chaos_recovery_tests(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create bounded chaos and recovery experiments with explicit safety controls."""

    _exact_inputs(inputs, "steady_state", "experiments", "dependencies")
    requirements = _requirements(inputs)
    steady_state = [
        {
            "invariant_id": require_resource_id(item.get("invariant_id"), "steady_state[].invariant_id"),
            "assertion": require_exact_text(item.get("assertion"), "steady_state[].assertion", maximum=4096),
            "measurement": require_text(item.get("measurement"), "steady_state[].measurement"),
            "tolerance": strict_json(item.get("tolerance"), "steady_state[].tolerance"),
        }
        for item in _objects(inputs, "steady_state")
    ]
    experiments: list[dict[str, Any]] = []
    for item in _objects(inputs, "experiments"):
        environment = require_resource_id(item.get("environment"), "experiments[].environment")
        if environment.casefold() in {"prod", "production", "live"}:
            raise ContractError("production chaos is not authorized by this local Skill")
        experiments.append(
            {
                "experiment_id": require_resource_id(item.get("experiment_id"), "experiments[].experiment_id"),
                "environment": environment,
                "fault_type": require_resource_id(item.get("fault_type"), "experiments[].fault_type"),
                "target": require_resource_id(item.get("target"), "experiments[].target"),
                "blast_radius": require_exact_text(item.get("blast_radius"), "experiments[].blast_radius", maximum=2048),
                "abort_conditions": _strings(item.get("abort_conditions"), "experiments[].abort_conditions", required=True),
                "rollback_steps": _strings(item.get("rollback_steps"), "experiments[].rollback_steps", required=True),
                "rto_seconds": _number(item.get("rto_seconds"), "experiments[].rto_seconds"),
                "rpo_seconds": _number(item.get("rpo_seconds"), "experiments[].rpo_seconds"),
            }
        )
    dependencies = [
        {
            "dependency_id": require_resource_id(item.get("dependency_id"), "dependencies[].dependency_id"),
            "timeout_ms": int(_number(item.get("timeout_ms"), "dependencies[].timeout_ms", minimum=1)),
            "retry_limit": int(_number(item.get("retry_limit"), "dependencies[].retry_limit")),
            "circuit_breaker": _bool(item.get("circuit_breaker"), "dependencies[].circuit_breaker"),
            "fallback": require_exact_text(item.get("fallback"), "dependencies[].fallback", maximum=2048),
        }
        for item in _objects(inputs, "dependencies")
    ]
    recipes = (
        ("steady-state", "measure-steady-state", "invariant", "the pre-fault business invariant is established", False),
        ("latency-timeout", "inject-dependency-latency", "timing", "timeouts and retries do not amplify load", True),
        ("network-error", "inject-network-error", "state", "isolation, circuit breaking, and fallback are bounded", True),
        ("process-node-failure", "terminate-isolated-node", "state", "traffic and work recover without duplicate effects", True),
        ("resource-exhaustion", "exhaust-bounded-resource", "resource", "degradation and abort controls protect the system", True),
        ("write-idempotency-compensation", "interrupt-write-and-retry", "data", "writes converge without duplicate or half-complete state", True),
        ("post-recovery-convergence", "restore-dependency-and-observe", "invariant", "traffic, queues, caches, and data converge", True),
        ("backup-dr-replay", "plan-backup-restore-and-failover", "data", "RTO, RPO, and business data are independently verified", True),
    )
    cases = _recipes(requirements, domain="resilience", recipes=recipes)
    blockers = []
    if not steady_state:
        blockers.append("STEADY_STATE_INVARIANTS_REQUIRED")
    if not experiments:
        blockers.append("BOUNDED_FAILURE_EXPERIMENTS_REQUIRED")
    if not dependencies:
        blockers.append("DEPENDENCY_RESILIENCE_MODEL_REQUIRED")
    return _result(
        code="RESILIENCE_CHAOS_RECOVERY_PLAN_GENERATED",
        cases=cases,
        blockers=blockers,
        outputs={
            "steady_state": steady_state,
            "experiments": experiments,
            "dependencies": dependencies,
            "production_execution_authorized": False,
            "chaos_execution": "NOT_RUN",
            "backup_restore_execution": "NOT_RUN",
            "physical_effects": "NOT_RUN",
        },
    )
