#!/usr/bin/env python3
"""Batch-specific domain contracts for the repository migration runtime.

Each registered handler is a real callable with an exact operation, capability
set, safety controls, tool evidence roles, raw evidence roles, and Oracle
assertions.  The module never executes repository-selected commands; it
validates results emitted by an operator-approved native adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable


NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class DomainHandlerError(ValueError):
    pass


@dataclass(frozen=True)
class DomainPolicy:
    batch: int
    handler: str
    operation: str
    capabilities: tuple[str, ...]
    safety_controls: tuple[str, ...]


POLICY_SPECS: tuple[tuple[int, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (1, "source-baseline", "freeze-source-baseline", ("source-inventory", "immutable-fingerprint"), ("read-only-source", "content-addressed-evidence")),
    (2, "differential-replay", "run-differential-replay", ("deterministic-replay", "behavioral-difference"), ("isolated-execution", "replay-pinned")),
    (3, "semantic-frontend", "extract-semantic-frontend", ("parser-frontend", "typed-semantic-ir"), ("no-silent-drop", "source-trace")),
    (4, "directional-routes", "execute-directional-route", ("directed-route-lowering", "target-toolchain-build"), ("direction-isolated", "unsupported-explicit")),
    (5, "framework-adapters", "execute-framework-adapter", ("runtime-fingerprint", "framework-contract"), ("exact-version-tuple", "security-preserved")),
    (6, "supply-chain", "verify-supply-chain", ("dependency-graph", "sbom-provenance"), ("immutable-locks", "secret-free")),
    (7, "data-messaging", "migrate-data-messaging", ("schema-data-migration", "detail-reconciliation", "transaction-rollback"), ("disposable-data", "checksum-bound", "rollback-tested")),
    (8, "api-mesh", "migrate-api-mesh", ("api-contract", "traffic-policy"), ("authorization-preserved", "backward-compatible")),
    (9, "concurrency-native", "verify-concurrency-native", ("schedule-semantics", "resource-lifetime"), ("bounded-schedule", "no-race-suppression")),
    (10, "test-mutation-fuzz", "run-test-mutation-fuzz", ("mutation-detection", "fuzz-replay"), ("bounded-campaign", "seed-pinned")),
    (11, "domain-journey", "verify-domain-journey", ("journey-contract", "business-outcome"), ("tenant-isolated", "failure-path-tested")),
    (12, "production-migration", "exercise-production-migration", ("shadow-canary", "rollback-switch"), ("approval-required", "reversible-cutover")),
    (13, "evidence-certification", "compose-evidence-certification", ("evidence-graph", "independent-verification"), ("role-separated", "content-addressed")),
    (14, "formal-proof", "verify-formal-proof", ("proof-obligation", "solver-result"), ("bounded-claim", "unknown-fails-closed")),
    (15, "counterexample-repair", "repair-counterexample", ("counterexample-replay", "repair-validation"), ("minimized-counterexample", "no-test-weakening")),
    (16, "architecture-search", "search-target-architecture", ("candidate-evaluation", "constraint-selection"), ("bounded-search", "decision-trace")),
    (17, "workflow-execution", "execute-migration-workflow", ("checkpoint-recovery", "compensation"), ("idempotent-steps", "fencing-protected")),
    (18, "project-generation", "generate-complete-project", ("blueprint-lowering", "target-build"), ("source-trace", "no-permissive-stub")),
    (19, "generator-routes", "execute-generator-route", ("route-generator", "compiler-validation"), ("direction-isolated", "exact-toolchain")),
    (20, "skill-runtime", "execute-skill-runtime", ("skill-contract", "runtime-install"), ("least-privilege", "collision-safe")),
    (21, "capability-closure", "evaluate-capability-closure", ("requirement-trace", "closure-decision"), ("missing-visible", "evidence-bound")),
    (22, "business-line", "verify-business-line", ("value-stream", "exception-handling"), ("actor-authorized", "compensation-tested")),
    (23, "cross-domain-journey", "verify-cross-domain-journey", ("saga-orchestration", "journey-reconciliation"), ("tenant-isolated", "replayable")),
    (24, "data-lineage", "verify-data-lineage", ("write-read-lineage", "authority-mapping"), ("immutable-source", "sensitive-data-minimized")),
    (25, "data-reconciliation", "reconcile-domain-data", ("detail-reconciliation", "repair-workflow"), ("no-aggregate-only", "money-exact")),
    (26, "admin-control-plane", "verify-admin-control-plane", ("admin-journey", "audit-event"), ("least-privilege", "tenant-isolated")),
    (27, "identity-authorization", "verify-identity-authorization", ("authentication", "authorization-policy"), ("fail-closed", "separation-of-duties")),
    (28, "usability-operations", "verify-usability-operations", ("task-completion", "recovery-state"), ("accessibility-preserved", "privacy-minimized")),
    (29, "regression-assurance", "run-regression-assurance", ("impacted-tests", "regression-evidence"), ("no-test-weakening", "baseline-frozen")),
    (30, "ha-dr", "exercise-ha-dr", ("failover-recovery", "backup-restore"), ("fault-isolated", "rto-rpo-recorded")),
    (31, "transaction-correctness", "verify-transaction-correctness", ("idempotency", "transaction-isolation"), ("deterministic-schedule", "conservation-checked")),
    (32, "performance-capacity", "verify-performance-capacity", ("workload-model", "latency-throughput"), ("bounded-load", "budget-enforced")),
    (33, "security-protection", "verify-security-protection", ("threat-control", "data-protection"), ("least-privilege", "secret-free")),
    (34, "provider-reliability", "verify-provider-reliability", ("provider-identity", "provider-operation", "cleanup-reconciliation"), ("least-privilege", "isolated-resources", "cleanup-tested")),
    (35, "go-live", "evaluate-go-live", ("release-gate", "production-acceptance"), ("approval-required", "rollback-ready")),
    (36, "production-operations", "verify-production-operations", ("slo-incident", "support-readiness"), ("oncall-owned", "evidence-expiring")),
    (37, "source-retirement", "verify-source-retirement", ("coexistence-exit", "data-portability"), ("decommission-approved", "restore-retained")),
    (38, "final-assurance", "evaluate-final-assurance", ("assurance-case", "residual-risk"), ("independent-review", "failed-gates-propagate")),
)


POLICIES = {item[0]: DomainPolicy(*item) for item in POLICY_SPECS}
BY_HANDLER = {policy.handler: policy for policy in POLICIES.values()}
if len(POLICIES) != 38 or sorted(POLICIES) != list(range(1, 39)) or len(BY_HANDLER) != 38:
    raise RuntimeError("repository migration domain policies must cover 38 unique handlers")


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def contract_for_batch(batch: int) -> dict[str, Any]:
    policy = POLICIES[batch]
    return {
        "handler": policy.handler,
        "contract_version": "1.0",
        "operation": policy.operation,
        "capabilities": list(policy.capabilities),
        "safety_controls": list(policy.safety_controls),
    }


def evidence_role(policy: DomainPolicy, capability: str) -> str:
    return f"domain:{policy.handler}:{capability}"


def _validate(policy: DomainPolicy, contract: Any, oracle_id: str, tools: list[dict[str, Any]],
              assertions: list[dict[str, Any]], raw_roles: set[str], decision: str) -> list[dict[str, str]]:
    required = {"handler", "contract_version", "operation", "capabilities", "safety_controls"}
    if not isinstance(contract, dict) or set(contract) != required:
        raise DomainHandlerError(f"Batch {policy.batch} domain contract fields are invalid")
    expected = contract_for_batch(policy.batch)
    if contract != expected:
        raise DomainHandlerError(f"Batch {policy.batch} domain contract does not match handler {policy.handler}")
    if any(not NAME_RE.fullmatch(item) for item in (*policy.capabilities, *policy.safety_controls)):
        raise DomainHandlerError(f"Batch {policy.batch} policy contains an invalid capability/control name")
    tool_roles = {item.get("evidence_role") for item in tools if item.get("exit_code") == 0}
    assertion_by_name: dict[str, dict[str, Any]] = {}
    for item in assertions:
        name = item.get("name")
        if not isinstance(name, str) or not name.startswith(oracle_id + ":") or name in assertion_by_name:
            raise DomainHandlerError(f"Batch {policy.batch} assertions are not uniquely bound to {oracle_id}")
        assertion_by_name[name] = item
    checks: list[dict[str, str]] = [{
        "name": f"domain-handler:{policy.handler}", "outcome": "PASS",
        "detail": f"operation={policy.operation}; contract={canonical_digest(contract)}",
    }]
    operation_name = f"{oracle_id}:operation:{policy.operation}"
    if operation_name not in assertion_by_name:
        raise DomainHandlerError(f"Batch {policy.batch} lacks operation assertion {operation_name}")
    required_names = [operation_name]
    for capability in policy.capabilities:
        role = evidence_role(policy, capability)
        assertion_name = f"{oracle_id}:capability:{capability}"
        if role not in tool_roles or role not in raw_roles:
            raise DomainHandlerError(f"Batch {policy.batch} capability {capability} lacks matching tool and raw evidence role")
        if assertion_name not in assertion_by_name:
            raise DomainHandlerError(f"Batch {policy.batch} lacks capability assertion {assertion_name}")
        required_names.append(assertion_name)
        checks.append({"name": f"domain-capability:{capability}", "outcome": assertion_by_name[assertion_name]["outcome"], "detail": role})
    for control in policy.safety_controls:
        assertion_name = f"{oracle_id}:safety:{control}"
        if assertion_name not in assertion_by_name:
            raise DomainHandlerError(f"Batch {policy.batch} lacks safety assertion {assertion_name}")
        required_names.append(assertion_name)
        checks.append({"name": f"domain-safety:{control}", "outcome": assertion_by_name[assertion_name]["outcome"], "detail": policy.operation})
    if decision == "PASS" and any(assertion_by_name[name].get("outcome") != "PASS" for name in required_names):
        raise DomainHandlerError(f"Batch {policy.batch} PASS contradicts its domain contract assertions")
    return checks


def _make_handler(policy: DomainPolicy) -> Callable[..., list[dict[str, str]]]:
    def handler(contract: Any, oracle_id: str, tools: list[dict[str, Any]], assertions: list[dict[str, Any]],
                raw_roles: set[str], decision: str) -> list[dict[str, str]]:
        return _validate(policy, contract, oracle_id, tools, assertions, raw_roles, decision)
    handler.__name__ = policy.handler.replace("-", "_")
    handler.__qualname__ = handler.__name__
    return handler


HANDLERS = {policy.handler: _make_handler(policy) for policy in POLICIES.values()}


def execute_handler(batch: int, registered_handler: str, contract: Any, oracle_id: str,
                    tools: list[dict[str, Any]], assertions: list[dict[str, Any]],
                    raw_roles: set[str], decision: str) -> list[dict[str, str]]:
    policy = POLICIES.get(batch)
    handler = HANDLERS.get(registered_handler)
    if policy is None or handler is None or policy.handler != registered_handler:
        raise DomainHandlerError(f"Batch {batch} has no callable domain handler")
    return handler(contract, oracle_id, tools, assertions, raw_roles, decision)
