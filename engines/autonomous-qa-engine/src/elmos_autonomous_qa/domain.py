"""Pure, repository-owned autonomous QA domain operations.

These functions implement the portable portions of the forty source Skills.
They deliberately produce plans or fail-closed decisions for effects that need
an isolated runner, an SCM worktree, a signer, or an external verifier.  The
durable control plane and artifact publisher live in dedicated modules.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from .adapters import (
    AdapterContractError,
    Capability,
    adapter_for,
)
from .canonical import normalize_relative_path
from .contracts import (
    ContractError,
    digest_bytes,
    digest_json,
    require_exact_text,
    require_resource_id,
    require_text,
    strict_json,
)


MODES = frozenset({"plan-only", "generate", "verify", "repair", "certify", "continuous"})
PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
TERMINAL_RESULTS = frozenset({"PASSED", "FAILED", "BLOCKED", "FLAKY_CONFIRMED", "NOT_APPLICABLE"})
BAD_RESULT_STATES = frozenset({"FAILED", "BLOCKED", "FLAKY_CONFIRMED", "NOT_RUN", "UNKNOWN", "SKIPPED"})
REQUIREMENT_ID = re.compile(r"^(?:REQ|CONSTRAINT|UXR|NFR|AC)-[A-Za-z0-9._-]+$")
SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
FORBIDDEN_PATCH_MARKERS = (
    "assert true",
    "asserttrue(true)",
    "@disabled",
    "pytest.mark.skip",
    "test.skip(",
    "describe.skip(",
    "quality_gate",
    "evidence_policy",
    "authorization_bypass",
    "thread.sleep(",
    "time.sleep(",
)
MAX_DOMAIN_ITEMS = 50_000
TEST_TYPES = frozenset(
    {
        "unit",
        "component",
        "functional",
        "api",
        "contract",
        "database",
        "migration",
        "message",
        "workflow",
        "ui_e2e",
        "visual",
        "accessibility",
        "compatibility",
        "performance",
        "load",
        "stress",
        "spike",
        "soak",
        "capacity",
        "security",
        "fuzz",
        "property",
        "mutation",
        "resilience",
        "chaos",
        "recovery",
    }
)
ORACLE_KINDS = frozenset(
    {
        "value",
        "state",
        "data",
        "event",
        "security",
        "timing",
        "resource",
        "visual",
        "accessibility",
        "invariant",
        "differential",
    }
)
TEST_CASE_FIELDS = frozenset(
    {
        "test_case_id",
        "title",
        "test_type",
        "priority",
        "required",
        "requirement_refs",
        "risk_tags",
        "preconditions",
        "parameters",
        "steps",
        "oracles",
        "evidence_requirements",
        "cleanup",
        "executor",
        "stability",
        "estimated_duration_seconds",
        "materialization",
    }
)
TEST_CASE_REQUIRED_FIELDS = frozenset(
    {
        "test_case_id",
        "title",
        "test_type",
        "priority",
        "required",
        "requirement_refs",
        "preconditions",
        "steps",
        "oracles",
        "evidence_requirements",
        "cleanup",
        "executor",
    }
)
STEP_FIELDS = frozenset(
    {
        "step_id",
        "action",
        "input",
        "timeout_ms",
        "side_effect",
        "idempotency_key",
        "cleanup_ref",
    }
)
ORACLE_FIELDS = frozenset(
    {"oracle_id", "kind", "assertion", "tolerance", "source"}
)
EXECUTOR_FIELDS = frozenset(
    {"adapter_key", "capability", "parameters", "environment_profile"}
)
TRIVIAL_ORACLES = frozenset(
    {
        "true",
        "success",
        "succeeded",
        "passed",
        "exit code 0",
        "process succeeded",
        "result is not none",
        "value is not none",
    }
)
ARTIFACT_CATEGORIES = frozenset(
    {"project", "test", "evidence", "coverage", "report", "log", "patch", "certificate"}
)
MATERIALIZATION_PROFILES: Mapping[str, tuple[str, str]] = {
    "java-maven": ("test_", "Test.java"),
    "java-gradle": ("test_", "Test.java"),
    "kotlin-maven": ("test_", "Test.kt"),
    "kotlin-gradle": ("test_", "Test.kt"),
    "python": ("test_", ".py"),
    "dotnet": ("Test", "Tests.cs"),
    "rust": ("test_", ".rs"),
    "cmake-c-cpp": ("test_", ".cpp"),
    "php-composer": ("Test", "Test.php"),
    "javascript-node": ("", ".test.js"),
    "typescript-node": ("", ".test.ts"),
    "react": ("", ".test.tsx"),
    "vue": ("", ".spec.ts"),
    "objective-c-xcode": ("Test", "Tests.m"),
    "swift-package": ("Test", "Tests.swift"),
    "swift-xcode": ("Test", "Tests.swift"),
    "flutter": ("", "_test.dart"),
}
FILE_LAYOUT_PATTERNS = frozenset(
    {
        "*_test.go",
        "*_test.c",
        "*_test.cpp",
        "*.test.js",
        "*.spec.js",
        "*.test.ts",
        "*.spec.ts",
        "src/**/*.test.*",
        "src/**/*.spec.*",
    }
)


def _objects(value: Any, field: str, *, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a non-empty array")
    if any(not isinstance(item, Mapping) for item in value):
        raise ContractError(f"{field} items must be objects")
    if len(value) > MAX_DOMAIN_ITEMS:
        raise ContractError(f"{field} exceeds the item limit")
    return list(value)


def _strings(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a non-empty array")
    if len(value) > MAX_DOMAIN_ITEMS:
        raise ContractError(f"{field} exceeds the item limit")
    return [require_text(item, f"{field}[]", maximum=2048) for item in value]


def _digest(value: Any, field: str) -> str:
    text = require_text(value, field, maximum=80)
    if not SHA256.fullmatch(text):
        raise ContractError(f"{field} must be a SHA-256 digest")
    return "sha256:" + text.removeprefix("sha256:")


def _exact_fields(
    value: Mapping[str, Any],
    *,
    field: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> None:
    if any(not isinstance(key, str) for key in value):
        raise ContractError(f"{field} field names must be strings")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise ContractError(f"{field} contains unsupported fields: {sorted(unknown)}")
    if missing:
        raise ContractError(f"{field} is missing required fields: {sorted(missing)}")


def _unique(values: Sequence[str], field: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ContractError(f"{field} may not contain duplicates")
    return list(values)


def _unique_casefold(values: Sequence[str], field: str) -> list[str]:
    folded = [value.casefold() for value in values]
    if len(set(folded)) != len(folded):
        raise ContractError(f"{field} may not contain case-insensitive duplicates")
    return list(values)


def _layout_matches(pattern: str, layout: str) -> bool:
    """Match one declared adapter layout without treating it as authority."""

    if not any(token in pattern for token in "*?["):
        return layout == pattern
    # PurePath.match is anchored by path segments and does not touch the
    # filesystem.  A declared filename glob is not a materialization directory.
    if pattern in FILE_LAYOUT_PATTERNS:
        return False
    return PurePosixPath(layout).match(pattern)


def _coverage(required: Sequence[str], mapped: Iterable[str]) -> float:
    expected = set(required)
    if not expected:
        return 1.0
    return len(expected & set(mapped)) / len(expected)


def _unified_diff_paths(diff: str) -> tuple[str, ...]:
    """Extract the exact repository paths declared by a unified diff.

    This is deliberately only an identity check.  It does not claim that text
    parsing proves patch semantics or that the patch has been applied.
    """

    paths: set[str] = set()
    lines = diff.splitlines()
    has_hunk = any(line.startswith("@@ ") for line in lines)
    has_change = any(
        line.startswith(("+", "-")) and not line.startswith(("+++ ", "--- "))
        for line in lines
    )
    if not has_hunk or not has_change:
        raise ContractError("diff must contain a unified-diff hunk and change")
    for line in lines:
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].split("\t", 1)[0]
        if raw == "/dev/null":
            continue
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        try:
            paths.add(normalize_relative_path(raw))
        except ValueError as exc:
            raise ContractError("diff declares an unsafe or non-canonical path") from exc
    if not paths:
        raise ContractError("diff must declare at least one unified-diff path")
    return tuple(sorted(paths))


def _repair_risk(paths: Sequence[str], semantic_tags: Iterable[str]) -> str:
    tags = {value.casefold() for value in semantic_tags}
    path_tokens: set[str] = set()
    for path in paths:
        for part in PurePosixPath(path).parts:
            path_tokens.update(
                token
                for token in re.split(r"[^a-z0-9]+", part.casefold())
                if token
            )
    r3 = {
        "authentication",
        "authorization",
        "payment",
        "payments",
        "cryptography",
        "migration",
        "migrations",
        "infrastructure",
        "production",
        "security",
        "iam",
    }
    r2 = {
        "transaction",
        "concurrency",
        "public-api",
        "shared-library",
        "cross-service",
        "database",
    }
    return (
        "R3"
        if tags & r3 or path_tokens & r3
        else "R2"
        if tags & r2 or path_tokens & r2
        else "R1"
    )


def create_run_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    mode = require_text(inputs.get("mode"), "mode")
    if mode not in MODES:
        raise ContractError("mode is unsupported")
    context = inputs.get("_runtime_context")
    if not isinstance(context, Mapping):
        raise ContractError("trusted runtime context is required")
    key = require_text(context.get("idempotency_key"), "runtime.idempotency_key", maximum=200)
    tenant_id = require_resource_id(context.get("tenant_id"), "runtime.tenant_id")
    project_id = require_resource_id(context.get("project_id"), "runtime.project_id")
    snapshot_ref = _digest(inputs.get("snapshot_ref"), "snapshot_ref")
    run_id = "run-" + digest_json(
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "mode": mode,
            "snapshot_ref": snapshot_ref,
            "idempotency_key": key,
        }
    )[7:31]
    states = ["CREATED", "INGESTING", "PLANNING"]
    if mode != "plan-only":
        states.extend(["GENERATING", "MATERIALIZING_TEST_ARTIFACTS", "PUBLISHING_OUTPUT"])
    return {
        "state": "SUCCEEDED",
        "code": "QA_RUN_CONTRACT_CREATED",
        "outputs": {
            "run_id": run_id,
            "mode": mode,
            "legal_initial_states": states,
            "output_required": mode != "plan-only",
            "direct_product_execution": False,
            "tenant_bound": True,
            "project_bound": True,
        },
    }


def ingest_snapshot(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    sources = _objects(inputs.get("sources"), "sources")
    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen: dict[str, str] = {}
    seen_source_ids: set[str] = set()
    for index, source in enumerate(sources):
        source_id = require_resource_id(source.get("source_id"), f"sources[{index}].source_id")
        if source_id in seen_source_ids:
            raise ContractError(f"duplicate source_id: {source_id}")
        seen_source_ids.add(source_id)
        uri = require_text(source.get("uri"), f"sources[{index}].uri", maximum=1024)
        required = source.get("required")
        if not isinstance(required, bool):
            raise ContractError("source.required must be boolean")
        raw = source.get("content")
        supplied = source.get("content_hash")
        if raw is None and supplied is None:
            blockers.append(f"{source_id}:CONTENT_UNAVAILABLE")
            digest = None
            status = "failed"
        elif raw is None:
            # A claimed digest identifies proposed bytes but proves neither
            # possession nor parsing.  Keep the identity while failing closed.
            digest = _digest(supplied, "content_hash")
            status = "partial"
            blockers.append(f"{source_id}:CONTENT_BYTES_NOT_VERIFIED")
        else:
            raw = require_exact_text(
                raw, "source.content", maximum=16 * 1024 * 1024
            )
            actual = digest_bytes(raw.encode("utf-8"))
            if supplied is not None and actual != _digest(supplied, "content_hash"):
                raise ContractError(f"source digest mismatch: {source_id}")
            digest = actual
            status = require_text(source.get("status", "parsed"), "source.status")
            if status not in {"parsed", "partial", "failed"}:
                raise ContractError("source.status is invalid")
            if required and status != "parsed":
                blockers.append(f"{source_id}:{status.upper()}")
        previous = seen.get(uri.casefold())
        if previous is not None and previous != digest:
            raise ContractError(f"same source URI has conflicting content: {uri}")
        seen[uri.casefold()] = digest or ""
        normalized.append(
            {
                "source_id": source_id,
                "uri": uri,
                "kind": require_text(source.get("kind", "other"), "source.kind"),
                "required": required,
                "status": status,
                "content_hash": digest,
            }
        )
    snapshot_id = "snapshot-" + digest_json(normalized)[7:39]
    return {
        "state": "PARTIAL" if blockers else "SUCCEEDED",
        "code": "SNAPSHOT_BLOCKED" if blockers else "SNAPSHOT_FROZEN",
        "outputs": {"snapshot_id": snapshot_id, "sources": normalized, "blockers": blockers},
    }


def normalize_requirements(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_requirements = _objects(inputs.get("requirements"), "requirements")
    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_requirements):
        requirement_id = require_resource_id(
            raw.get("requirement_id"), f"requirements[{index}].requirement_id"
        )
        if not REQUIREMENT_ID.fullmatch(requirement_id) or requirement_id in seen:
            raise ContractError(f"invalid or duplicate requirement_id: {requirement_id}")
        seen.add(requirement_id)
        priority = require_text(raw.get("priority"), "requirement.priority")
        if priority not in PRIORITIES:
            raise ContractError("requirement.priority is invalid")
        acceptance = _unique(
            _strings(
                raw.get("acceptance_criteria", []),
                "acceptance_criteria",
                allow_empty=True,
            ),
            "acceptance_criteria",
        )
        ambiguities = _unique(
            _strings(raw.get("ambiguities", []), "ambiguities", allow_empty=True),
            "ambiguities",
        )
        source_refs = _unique(
            _strings(raw.get("source_refs"), "requirement.source_refs"),
            "requirement.source_refs",
        )
        status = require_text(raw.get("status", "ready"), "requirement.status")
        if status not in {"ready", "ambiguous", "conflicting", "blocked", "deprecated"}:
            raise ContractError("requirement.status is invalid")
        required = raw.get("required", True)
        if not isinstance(required, bool):
            raise ContractError("requirement.required must be boolean")
        if required and (not acceptance or ambiguities or status != "ready"):
            blockers.append(requirement_id)
        normalized.append(
            {
                "requirement_id": requirement_id,
                "kind": require_text(raw.get("kind", "functional"), "requirement.kind"),
                "title": require_text(raw.get("title"), "requirement.title", maximum=1024),
                "statement": require_exact_text(
                    raw.get("statement"), "requirement.statement", maximum=8192
                ),
                "priority": priority,
                "required": required,
                "source_refs": source_refs,
                "acceptance_criteria": acceptance,
                "ambiguities": ambiguities,
                "status": status,
            }
        )
    return {
        "state": "PARTIAL" if blockers else "SUCCEEDED",
        "code": "REQUIREMENTS_NEED_CLARIFICATION" if blockers else "REQUIREMENTS_NORMALIZED",
        "outputs": {"requirements": normalized, "blocking_requirement_ids": blockers},
    }


def build_traceability(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    requirements = _objects(inputs.get("requirements"), "requirements")
    tests = _objects(inputs.get("tests", []), "tests", allow_empty=True)
    artifacts = _objects(inputs.get("artifacts", []), "artifacts", allow_empty=True)
    required_ids: list[str] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    mapped: set[str] = set()
    materialized: set[str] = set()
    requirement_ids: set[str] = set()
    node_ids: set[str] = set()
    for item in requirements:
        rid = require_resource_id(item.get("requirement_id"), "requirement_id")
        if rid in requirement_ids:
            raise ContractError(f"duplicate requirement_id: {rid}")
        requirement_ids.add(rid)
        node_ids.add(rid)
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ContractError("requirement.required must be boolean")
        if required:
            required_ids.append(rid)
        nodes.append(
            {
                "node_id": rid,
                "kind": rid.split("-", 1)[0],
                "label": require_text(item.get("title", rid), "requirement.title", maximum=1024),
            }
        )
    artifact_by_test: dict[str, list[str]] = defaultdict(list)
    artifact_ids: set[str] = set()
    for artifact in artifacts:
        artifact_id = require_resource_id(artifact.get("artifact_id"), "artifact_id")
        if artifact_id in artifact_ids or artifact_id in node_ids:
            raise ContractError(f"duplicate graph node or artifact_id: {artifact_id}")
        artifact_ids.add(artifact_id)
        node_ids.add(artifact_id)
        try:
            artifact_path = normalize_relative_path(
                require_text(artifact.get("path"), "artifact.path", maximum=1024)
            )
        except ValueError as exc:
            raise ContractError("artifact path is unsafe") from exc
        nodes.append(
            {"node_id": artifact_id, "kind": "TEST_FILE", "label": artifact_path}
        )
        test_refs = _strings(
            artifact.get("test_case_refs", []), "test_case_refs", allow_empty=True
        )
        if len(set(test_refs)) != len(test_refs):
            raise ContractError(f"artifact {artifact_id} has duplicate test references")
        for test_ref in test_refs:
            artifact_by_test[require_resource_id(test_ref, "test_case_ref")].append(
                artifact_id
            )
    test_ids: set[str] = set()
    for test in tests:
        test_id = require_resource_id(test.get("test_case_id"), "test_case_id")
        if test_id in test_ids or test_id in node_ids:
            raise ContractError(f"duplicate graph node or test_case_id: {test_id}")
        test_ids.add(test_id)
        node_ids.add(test_id)
        required = test.get("required", True)
        executable = test.get("executable", False)
        oracle_valid = test.get("oracle_valid", False)
        if not all(isinstance(value, bool) for value in (required, executable, oracle_valid)):
            raise ContractError("test required/executable/oracle_valid fields must be boolean")
        nodes.append(
            {
                "node_id": test_id,
                "kind": "TEST",
                "label": require_text(test.get("title", test_id), "test.title", maximum=1024),
            }
        )
        refs = _strings(test.get("requirement_refs"), "requirement_refs")
        if len(set(refs)) != len(refs):
            raise ContractError(f"duplicate requirement reference on test {test_id}")
        unknown = sorted(set(refs).difference(requirement_ids))
        if unknown:
            raise ContractError(f"test {test_id} references unknown requirements: {unknown}")
        for rid in refs:
            edges.append({"from": test_id, "to": rid, "kind": "verifies", "confidence": 1.0})
            if executable and oracle_valid:
                mapped.add(rid)
        for artifact_id in artifact_by_test.get(test_id, []):
            edges.append({"from": test_id, "to": artifact_id, "kind": "materialized_as", "confidence": 1.0})
            materialized.add(test_id)
    dangling_artifact_refs = sorted(set(artifact_by_test).difference(test_ids))
    if dangling_artifact_refs:
        raise ContractError(
            f"artifacts reference unknown test cases: {dangling_artifact_refs}"
        )
    missing = sorted(set(required_ids) - mapped)
    required_tests = [
        require_resource_id(item.get("test_case_id"), "test_case_id")
        for item in tests
        if item.get("required", True) is True
    ]
    unmaterialized = sorted(set(required_tests) - materialized)
    return {
        "state": "PARTIAL" if missing or unmaterialized else "SUCCEEDED",
        "code": "TRACEABILITY_GAPS" if missing or unmaterialized else "TRACEABILITY_COMPLETE",
        "outputs": {
            "graph_id": "graph-" + digest_json({"nodes": nodes, "edges": edges})[7:31],
            "nodes": nodes,
            "edges": edges,
            "coverage": _coverage(required_ids, mapped),
            "unmapped_required": missing,
            "unmaterialized_required_tests": unmaterialized,
        },
    }


def plan_coverage(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    requirements = _objects(inputs.get("requirements"), "requirements")
    budget = inputs.get("budget_seconds")
    if (
        not isinstance(budget, (int, float))
        or isinstance(budget, bool)
        or not math.isfinite(float(budget))
        or budget <= 0
    ):
        raise ContractError("budget_seconds must be positive")
    plans: list[dict[str, Any]] = []
    estimated = 0.0
    seen_requirement_ids: set[str] = set()
    for item in requirements:
        rid = require_resource_id(item.get("requirement_id"), "requirement_id")
        if rid in seen_requirement_ids:
            raise ContractError(f"duplicate requirement_id: {rid}")
        seen_requirement_ids.add(rid)
        priority = require_text(item.get("priority"), "priority")
        if priority not in PRIORITIES:
            raise ContractError("requirement priority is invalid")
        types = ["functional"]
        tags_list = _strings(
            item.get("risk_tags", []), "risk_tags", allow_empty=True
        )
        _unique_casefold(tags_list, "risk_tags")
        tags = {tag.casefold() for tag in tags_list}
        if tags & {"api", "contract"}:
            types.append("api")
        if tags & {"auth", "tenant", "security"}:
            types.append("security")
        if tags & {"ui", "ux"}:
            types.extend(["ui_e2e", "accessibility"])
        if tags & {"database", "migration"}:
            types.append("database")
        if tags & {"performance", "slo"}:
            types.append("performance")
        duration = (90 if priority in {"P0", "P1"} else 45) * len(types)
        estimated += duration
        plans.append({"requirement_id": rid, "priority": priority, "test_types": types, "estimated_seconds": duration})
    blockers = [] if estimated <= float(budget) else ["REQUIRED_SCOPE_EXCEEDS_BUDGET"]
    return {
        "state": "PARTIAL" if blockers else "SUCCEEDED",
        "code": "COVERAGE_BUDGET_BLOCKED" if blockers else "COVERAGE_PLANNED",
        "outputs": {"plans": plans, "estimated_seconds": estimated, "budget_seconds": budget, "blockers": blockers},
    }


def validate_test_dsl(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    cases = _objects(inputs.get("test_cases"), "test_cases")
    canonical: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for case in cases:
        _exact_fields(
            case,
            field="test_case",
            allowed=TEST_CASE_FIELDS,
            required=TEST_CASE_REQUIRED_FIELDS,
        )
        test_id = require_resource_id(case.get("test_case_id"), "test_case_id")
        if test_id in seen_case_ids:
            raise ContractError(f"duplicate test_case_id: {test_id}")
        seen_case_ids.add(test_id)
        title = require_text(case.get("title"), "test.title", maximum=512)
        test_type = require_text(case.get("test_type"), "test.test_type")
        if test_type not in TEST_TYPES:
            raise ContractError(f"test {test_id} has an unsupported test_type")
        priority = require_text(case.get("priority"), "test.priority")
        if priority not in PRIORITIES:
            raise ContractError(f"test {test_id} has an invalid priority")
        required = case.get("required")
        if not isinstance(required, bool):
            raise ContractError(f"test {test_id} required must be boolean")
        requirement_refs = _unique(
            [
                require_resource_id(value, "requirement_refs[]")
                for value in _strings(case.get("requirement_refs"), "requirement_refs")
            ],
            "requirement_refs",
        )
        risk_tags = _unique_casefold(
            _strings(case.get("risk_tags", []), "risk_tags", allow_empty=True),
            "risk_tags",
        )
        preconditions = _unique(
            _strings(case.get("preconditions"), "preconditions", allow_empty=True),
            "preconditions",
        )
        cleanup = _unique(
            [
                require_resource_id(value, "cleanup[]")
                for value in _strings(case.get("cleanup"), "cleanup", allow_empty=True)
            ],
            "cleanup",
        )
        evidence_requirements = _unique(
            _strings(case.get("evidence_requirements"), "evidence_requirements"),
            "evidence_requirements",
        )
        steps = _objects(case.get("steps"), "steps")
        oracles = _objects(case.get("oracles"), "oracles")
        normalized_steps: list[dict[str, Any]] = []
        step_ids: set[str] = set()
        for step in steps:
            _exact_fields(
                step,
                field="test.step",
                allowed=STEP_FIELDS,
                required=frozenset({"step_id", "action"}),
            )
            step_id = require_resource_id(step.get("step_id"), "step.step_id")
            if step_id in step_ids:
                raise ContractError(f"test {test_id} has duplicate step_id {step_id}")
            step_ids.add(step_id)
            action = require_resource_id(step.get("action"), "step.action")
            timeout = step.get("timeout_ms", 30_000)
            if (
                not isinstance(timeout, int)
                or isinstance(timeout, bool)
                or not 1 <= timeout <= 3_600_000
            ):
                raise ContractError("step.timeout_ms must be an integer from 1 to 3600000")
            side_effect = step.get("side_effect", False)
            if not isinstance(side_effect, bool):
                raise ContractError("step.side_effect must be boolean")
            idempotency_key = step.get("idempotency_key")
            cleanup_ref = step.get("cleanup_ref")
            if side_effect:
                idempotency_key = require_text(
                    idempotency_key, "step.idempotency_key", maximum=200
                )
                cleanup_ref = require_resource_id(cleanup_ref, "step.cleanup_ref")
                if cleanup_ref not in cleanup:
                    raise ContractError(
                        f"test {test_id} side effect cleanup_ref is not declared"
                    )
            elif idempotency_key is not None or cleanup_ref is not None:
                raise ContractError(
                    f"test {test_id} non-side-effect step may not claim cleanup/idempotency"
                )
            normalized_steps.append(
                {
                    "step_id": step_id,
                    "action": action,
                    "input": strict_json(step.get("input"), "step.input"),
                    "timeout_ms": timeout,
                    "side_effect": side_effect,
                    "idempotency_key": idempotency_key,
                    "cleanup_ref": cleanup_ref,
                }
            )

        normalized_oracles: list[dict[str, Any]] = []
        oracle_ids: set[str] = set()
        for oracle in oracles:
            _exact_fields(
                oracle,
                field="test.oracle",
                allowed=ORACLE_FIELDS,
                required=frozenset({"oracle_id", "kind", "assertion"}),
            )
            oracle_id = require_resource_id(oracle.get("oracle_id"), "oracle.oracle_id")
            if oracle_id in oracle_ids:
                raise ContractError(f"test {test_id} has duplicate oracle_id {oracle_id}")
            oracle_ids.add(oracle_id)
            kind = require_text(oracle.get("kind"), "oracle.kind")
            if kind not in ORACLE_KINDS:
                raise ContractError(f"test {test_id} has an unsupported oracle kind")
            assertion = require_exact_text(
                oracle.get("assertion"), "oracle.assertion", maximum=8192
            )
            if assertion.strip().casefold().rstrip(".!;") in TRIVIAL_ORACLES:
                raise ContractError(f"test {test_id} has a trivial oracle")
            tolerance = strict_json(oracle.get("tolerance"), "oracle.tolerance")
            if tolerance is not None and (
                isinstance(tolerance, bool)
                or not isinstance(tolerance, (str, int, float))
            ):
                raise ContractError("oracle.tolerance must be text, number, or null")
            source = oracle.get("source")
            normalized_oracles.append(
                {
                    "oracle_id": oracle_id,
                    "kind": kind,
                    "assertion": assertion,
                    "tolerance": tolerance,
                    "source": require_text(source, "oracle.source", maximum=1024)
                    if source is not None
                    else None,
                }
            )

        executor = case.get("executor")
        if not isinstance(executor, Mapping):
            raise ContractError(f"test {test_id} executor must be an object")
        _exact_fields(
            executor,
            field="test.executor",
            allowed=EXECUTOR_FIELDS,
            required=frozenset({"adapter_key", "capability"}),
        )
        adapter_key = require_text(executor.get("adapter_key"), "executor.adapter_key")
        capability_name = require_text(executor.get("capability"), "executor.capability")
        parameters = executor.get("parameters", {})
        if not isinstance(parameters, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in parameters.items()
        ):
            raise ContractError("executor.parameters must be a string-to-string object")
        if len(parameters) > 128:
            raise ContractError("executor.parameters exceeds the entry limit")
        normalized_parameters = {
            require_text(key, "executor.parameters key", maximum=128): require_text(
                value, "executor.parameters value", maximum=4096
            )
            for key, value in parameters.items()
        }
        if len(normalized_parameters) != len(parameters):
            raise ContractError("executor.parameters contains normalized key collisions")
        try:
            adapter = adapter_for(adapter_key)
            capability = Capability(capability_name)
            proposal = adapter.plan(capability, parameters=normalized_parameters)
            commands = [
                {
                    "argv": list(command.argv),
                    "cwd": command.cwd,
                    "shell": command.shell,
                }
                for command in proposal.require_commands()
            ]
        except (AdapterContractError, ValueError) as exc:
            raise ContractError(
                f"test {test_id} has no exact repository command template"
            ) from exc
        duration = case.get("estimated_duration_seconds", 0.0)
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(float(duration))
            or duration < 0
        ):
            raise ContractError("estimated_duration_seconds must be finite and non-negative")
        stability = case.get("stability", {})
        if not isinstance(stability, Mapping):
            raise ContractError("test.stability must be an object")
        _exact_fields(
            stability,
            field="test.stability",
            allowed=frozenset({"deterministic", "retry_for_classification_max"}),
        )
        deterministic = stability.get("deterministic", True)
        retries = stability.get("retry_for_classification_max", 0)
        if not isinstance(deterministic, bool) or (
            not isinstance(retries, int)
            or isinstance(retries, bool)
            or not 0 <= retries <= 5
        ):
            raise ContractError("test.stability fields are invalid")
        materialization_value = case.get("materialization", {})
        if not isinstance(materialization_value, Mapping):
            raise ContractError("test.materialization must be an object")
        _exact_fields(
            materialization_value,
            field="test.materialization",
            allowed=frozenset(
                {
                    "planned_paths",
                    "artifact_refs",
                    "language",
                    "framework",
                    "native_test_target",
                    "validation_status",
                }
            ),
        )
        try:
            planned_paths = _unique(
                [
                    normalize_relative_path(path)
                    for path in _strings(
                        materialization_value.get("planned_paths", []),
                        "materialization.planned_paths",
                        allow_empty=True,
                    )
                ],
                "materialization.planned_paths",
            )
        except ValueError as exc:
            raise ContractError("materialization paths must be safe and canonical") from exc
        artifact_refs = _unique(
            [
                require_resource_id(value, "materialization.artifact_refs[]")
                for value in _strings(
                    materialization_value.get("artifact_refs", []),
                    "materialization.artifact_refs",
                    allow_empty=True,
                )
            ],
            "materialization.artifact_refs",
        )
        validation_status = materialization_value.get("validation_status", "planned")
        if validation_status not in {
            "planned",
            "generated",
            "syntax_valid",
            "buildable",
            "discovered",
            "executed",
            "certified",
            "blocked",
            "stale",
        }:
            raise ContractError("materialization.validation_status is invalid")
        materialization = {
            "planned_paths": planned_paths,
            "artifact_refs": artifact_refs,
            "language": require_text(
                materialization_value.get("language"),
                "materialization.language",
                maximum=128,
            )
            if materialization_value.get("language") is not None
            else None,
            "framework": require_text(
                materialization_value.get("framework"),
                "materialization.framework",
                maximum=128,
            )
            if materialization_value.get("framework") is not None
            else None,
            "native_test_target": require_text(
                materialization_value.get("native_test_target"),
                "materialization.native_test_target",
                maximum=1024,
            )
            if materialization_value.get("native_test_target") is not None
            else None,
            "validation_status": validation_status,
        }
        normalized_case = {
            "test_case_id": test_id,
            "title": title,
            "test_type": test_type,
            "priority": priority,
            "required": required,
            "requirement_refs": requirement_refs,
            "risk_tags": risk_tags,
            "preconditions": preconditions,
            "parameters": strict_json(case.get("parameters", {}), "test.parameters"),
            "steps": normalized_steps,
            "oracles": normalized_oracles,
            "evidence_requirements": evidence_requirements,
            "cleanup": cleanup,
            "executor": {
                "adapter_key": adapter_key,
                "capability": capability_name,
                "environment_profile": require_resource_id(
                    executor.get("environment_profile", "isolated-local"),
                    "executor.environment_profile",
                ),
                "command_plan_proposal": commands,
                "command_execution_performed": False,
                "adapter_qualification": "NOT_RUN",
                "trusted_probe_receipt": "NOT_RUN",
                "caller_qualification_accepted": False,
            },
            "stability": {
                "deterministic": deterministic,
                "retry_for_classification_max": retries,
            },
            "estimated_duration_seconds": float(duration),
            "materialization": materialization,
        }
        canonical.append(normalized_case)
    return {
        "state": "PARTIAL",
        "code": "TEST_DSL_VALIDATED_ADAPTER_UNQUALIFIED",
        "outputs": {
            "test_cases": canonical,
            "dsl_digest": digest_json(canonical),
            "arbitrary_code_embedded": False,
            "adapter_qualification": "NOT_RUN",
        },
    }


def generate_profile_cases(
    inputs: Mapping[str, Any], *, test_type: str, strategies: Sequence[str]
) -> Mapping[str, Any]:
    if test_type not in TEST_TYPES:
        raise ContractError("generator test_type is unsupported")
    normalized_strategies = [
        require_resource_id(strategy, "generator.strategy") for strategy in strategies
    ]
    if not normalized_strategies or len(set(normalized_strategies)) != len(
        normalized_strategies
    ):
        raise ContractError("generator strategies must be non-empty and unique")
    requirements = _objects(inputs.get("requirements"), "requirements")
    executor_template = inputs.get("executor")
    if executor_template is not None and not isinstance(executor_template, Mapping):
        raise ContractError("generator executor must be an object when supplied")
    cases: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for requirement in requirements:
        rid = require_resource_id(requirement.get("requirement_id"), "requirement_id")
        priority = require_text(requirement.get("priority", "P2"), "priority")
        if priority not in PRIORITIES:
            raise ContractError("requirement priority is invalid")
        required = requirement.get("required", True)
        if not isinstance(required, bool):
            raise ContractError("requirement.required must be boolean")
        criteria = _strings(
            requirement.get("acceptance_criteria", []),
            "acceptance_criteria",
            allow_empty=True,
        )
        generated_risk_tags = _unique_casefold(
            _strings(
                requirement.get("risk_tags", []),
                "requirement.risk_tags",
                allow_empty=True,
            ),
            "requirement.risk_tags",
        )
        assertion = criteria[0] if criteria else require_exact_text(
            requirement.get("statement"),
            "requirement.statement",
            maximum=8192,
        )
        title = require_text(
            requirement.get("title", rid), "requirement.title", maximum=400
        )
        for index, strategy in enumerate(normalized_strategies, start=1):
            case_id = f"TC-{test_type.upper().replace('_', '-')}-{rid}-{index:02d}"
            if len(case_id.encode("utf-8")) > 128:
                case_id = (
                    f"TC-{test_type.upper().replace('_', '-')}-"
                    f"{hashlib.sha256(rid.encode('utf-8')).hexdigest()[:24]}-{index:02d}"
                )
            case_id = require_resource_id(case_id, "generated.test_case_id")
            if case_id in seen_case_ids:
                raise ContractError("generated test_case_id collision")
            seen_case_ids.add(case_id)
            cases.append(
                {
                    "test_case_id": case_id,
                    "title": f"{strategy}: {title}",
                    "test_type": test_type,
                    "priority": priority,
                    "required": required,
                    "requirement_refs": [rid],
                    "risk_tags": generated_risk_tags,
                    "preconditions": [],
                    "parameters": {"strategy": strategy},
                    "steps": [
                        {
                            "step_id": f"step-{index:02d}",
                            "action": "verify-requirement",
                            "input": {"requirement_id": rid, "strategy": strategy},
                            "side_effect": False,
                        }
                    ],
                    "oracles": [
                        {
                            "oracle_id": f"oracle-{index:02d}",
                            "kind": "invariant",
                            "assertion": assertion,
                        }
                    ],
                    "evidence_requirements": ["structured-result", "adapter-raw-output"],
                    "cleanup": [],
                    "executor": {"binding_status": "UNBOUND"},
                    "materialization": {"validation_status": "planned"},
                }
            )
    if executor_template is not None:
        bound_cases = [
            {**case, "executor": dict(executor_template)} for case in cases
        ]
        validated = validate_test_dsl({"test_cases": bound_cases})
        return {
            "state": "PARTIAL",
            "code": f"{test_type.upper()}_CASE_PROPOSALS_GENERATED",
            "outputs": {
                "test_cases": validated["outputs"]["test_cases"],
                "generator_digest": digest_json(
                    {"type": test_type, "strategies": normalized_strategies}
                ),
                "dsl_digest": validated["outputs"]["dsl_digest"],
                "executor_binding": "CALLER_PROPOSAL",
                "trusted_probe_receipt": "NOT_RUN",
                "caller_qualification_accepted": False,
                "command_execution_performed": False,
            },
        }
    return {
        "state": "PARTIAL",
        "code": f"{test_type.upper()}_CASE_PROPOSALS_GENERATED",
        "outputs": {
            "test_cases": cases,
            "generator_digest": digest_json(
                {"type": test_type, "strategies": normalized_strategies}
            ),
            "executor_binding": "NOT_RUN",
            "dsl_validation": "BLOCKED_ADAPTER_BINDING_REQUIRED",
        },
    }


def plan_test_data(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    datasets = _objects(inputs.get("datasets"), "datasets")
    planned: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_ids: set[str] = set()
    for item in datasets:
        dataset_id = require_resource_id(item.get("dataset_id"), "dataset_id")
        if dataset_id in seen_ids:
            raise ContractError(f"duplicate dataset_id: {dataset_id}")
        seen_ids.add(dataset_id)
        source = require_text(item.get("source"), "dataset.source")
        classification = require_text(item.get("classification", "internal"), "dataset.classification")
        normalized_source = source.casefold()
        normalized_classification = classification.casefold()
        if normalized_source not in {
            "synthetic",
            "fixture",
            "generated",
            "sanitized-export",
            "production",
            "prod",
        }:
            raise ContractError("dataset.source is unsupported")
        if normalized_classification not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise ContractError("dataset.classification is unsupported")
        masked_value = item.get("masked", False)
        if not isinstance(masked_value, bool):
            raise ContractError("dataset.masked must be boolean")
        production_source = normalized_source in {"production", "prod"}
        if production_source or normalized_source == "sanitized-export":
            blockers.append(f"{dataset_id}:TRUSTED_SANITIZATION_RECEIPT_REQUIRED")
        planned.append(
            {
                "dataset_id": dataset_id,
                "source": normalized_source,
                "classification": normalized_classification,
                "caller_masked_assertion": masked_value,
                "trusted_sanitization_receipt": "NOT_RUN",
            }
        )
    return {
        "state": "BLOCKED" if blockers else "SUCCEEDED",
        "code": "TEST_DATA_POLICY_BLOCKED" if blockers else "TEST_DATA_PLANNED",
        "outputs": {"datasets": planned, "blockers": blockers, "tenant_isolation_required": True, "cleanup_required": True},
    }


def plan_environment(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = require_text(inputs.get("profile"), "profile")
    profile_tokens = set(re.split(r"[^a-z0-9]+", profile.casefold()))
    if profile_tokens & {"production", "prod"}:
        return {"state": "BLOCKED", "code": "PRODUCTION_ENVIRONMENT_DENIED", "outputs": {"profile": profile}}
    resources = _unique(_strings(inputs.get("resources"), "resources"), "resources")
    return {
        "state": "SUCCEEDED",
        "code": "ISOLATED_ENVIRONMENT_PLANNED",
        "outputs": {
            "profile": profile,
            "resources": sorted(set(resources)),
            "network_policy": "DENY_BY_DEFAULT",
            "lease_required": True,
            "cleanup_idempotent": True,
        },
    }


def plan_shards(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    tests = _objects(inputs.get("tests"), "tests")
    workers = inputs.get("workers", 1)
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1 or workers > 256:
        raise ContractError("workers must be an integer from 1 to 256")
    normalized_tests: list[tuple[str, float]] = []
    seen_ids: set[str] = set()
    for item in tests:
        test_id = require_resource_id(item.get("test_case_id"), "test_case_id")
        if test_id in seen_ids:
            raise ContractError(f"duplicate test_case_id: {test_id}")
        seen_ids.add(test_id)
        duration = item.get("estimated_seconds", 0)
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(float(duration))
            or duration < 0
            or duration > 31_536_000
        ):
            raise ContractError(
                "estimated_seconds must be finite and no greater than one year"
            )
        normalized_tests.append((test_id, float(duration)))
    shards: list[list[str]] = [[] for _ in range(min(workers, len(tests)))]
    ordered = sorted(normalized_tests, key=lambda item: (-item[1], item[0]))
    weights = [0.0] * len(shards)
    for test_id, duration in ordered:
        index = min(range(len(shards)), key=weights.__getitem__)
        shards[index].append(test_id)
        weights[index] += duration
    payload = [{"shard_id": f"shard-{i + 1:03d}", "test_case_ids": value, "fencing_token_required": True} for i, value in enumerate(shards)]
    return {"state": "SUCCEEDED", "code": "EXECUTION_SHARDS_PLANNED", "outputs": {"shards": payload, "plan_digest": digest_json(payload)}}


def verify_evidence(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = _objects(inputs.get("evidence"), "evidence")
    verified: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_ids: set[str] = set()
    for item in evidence:
        evidence_id = require_resource_id(item.get("evidence_id"), "evidence_id")
        if evidence_id in seen_ids:
            raise ContractError(f"duplicate evidence_id: {evidence_id}")
        seen_ids.add(evidence_id)
        expected = _digest(item.get("sha256"), "evidence.sha256")
        content = item.get("content")
        digest_matches = isinstance(content, str) and digest_bytes(
            content.encode("utf-8")
        ) == expected
        if not digest_matches:
            blockers.append(f"{evidence_id}:DIGEST_MISMATCH")
        replay = item.get("replay_command")
        replay_valid = not (
            not isinstance(replay, list)
            or not replay
            or len(replay) > 128
            or any(
                not isinstance(part, str)
                or not part
                or len(part.encode("utf-8")) > 4096
                or any(control in part for control in ("\x00", "\n", "\r"))
                for part in replay
            )
        )
        if not replay_valid:
            blockers.append(f"{evidence_id}:REPLAY_DESCRIPTOR_INVALID")
        self_checked = not any(
            value.startswith(evidence_id + ":") for value in blockers
        )
        verified.append(
            {
                "evidence_id": evidence_id,
                "sha256": expected,
                # Caller commands are never promoted to an executable plan.
                "replay_descriptor_digest": digest_json(replay)
                if replay_valid
                else None,
                "replay_execution_authorized": False,
                "digest_self_checked": self_checked,
                "verified": False,
            }
        )
    return {
        "state": "BLOCKED",
        "code": "EVIDENCE_INVALID"
        if blockers
        else "TRUSTED_EVIDENCE_RECEIPT_REQUIRED",
        "outputs": {
            "evidence": verified,
            "blockers": blockers,
            "digest_self_check_completed": not blockers,
            "independent_verification": "NOT_RUN",
        },
        "implementation_state": "LOCAL_VALIDATED",
    }


def classify_flaky(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    attempts = _objects(inputs.get("attempts"), "attempts")
    by_test: dict[str, list[str]] = defaultdict(list)
    seen_attempts: set[str] = set()
    for attempt in attempts:
        attempt_id = require_resource_id(attempt.get("attempt_id"), "attempt_id")
        if attempt_id in seen_attempts:
            raise ContractError(f"duplicate attempt_id: {attempt_id}")
        seen_attempts.add(attempt_id)
        test_id = require_resource_id(attempt.get("test_case_id"), "test_case_id")
        status = require_text(attempt.get("status"), "attempt.status").upper()
        if status not in {"PASSED", "FAILED", "BLOCKED"}:
            raise ContractError("attempt status is invalid")
        by_test[test_id].append(status)
    profiles = []
    for test_id, statuses in sorted(by_test.items()):
        state = "FLAKY_CONFIRMED" if "PASSED" in statuses and "FAILED" in statuses else statuses[-1]
        profiles.append(
            {
                "test_case_id": test_id,
                "status": state,
                "attempts": statuses,
                "first_failure_index": statuses.index("FAILED")
                if "FAILED" in statuses
                else None,
                "all_attempts_retained": True,
            }
        )
    blocked = [item["test_case_id"] for item in profiles if item["status"] == "FLAKY_CONFIRMED"]
    return {"state": "PARTIAL" if blocked else "SUCCEEDED", "code": "FLAKY_TESTS_CONFIRMED" if blocked else "FLAKY_CLASSIFICATION_COMPLETE", "outputs": {"profiles": profiles, "gate_blockers": blocked}}


def triage_defects(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    failures = _objects(inputs.get("failures", []), "failures", allow_empty=True)
    clusters: dict[str, dict[str, Any]] = {}
    seen_failures: set[tuple[str, str]] = set()
    for failure in failures:
        test_id = require_resource_id(failure.get("test_case_id"), "test_case_id")
        fingerprint = require_text(failure.get("fingerprint"), "fingerprint", maximum=512)
        failure_key = (test_id, fingerprint)
        if failure_key in seen_failures:
            raise ContractError("duplicate failure observation")
        seen_failures.add(failure_key)
        if "root_cause_confidence" not in failure:
            raise ContractError("root_cause_confidence is required for each failure")
        confidence = failure.get("root_cause_confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise ContractError("root_cause_confidence must be a number from 0 to 1")
        reproduction = failure.get("reproduction_command", [])
        if (
            not isinstance(reproduction, list)
            or not reproduction
            or len(reproduction) > 128
            or any(
                not isinstance(token, str)
                or not token
                or len(token.encode("utf-8")) > 4096
                or any(control in token for control in ("\x00", "\n", "\r"))
                for token in reproduction
            )
        ):
            raise ContractError("reproduction_command must be a structured argv array")
        reproduction_digest = digest_json(reproduction)
        existing = clusters.get(fingerprint)
        if existing is not None and (
            existing["reproduction_descriptor_digest"] != reproduction_digest
            or existing["root_cause_confidence"] != float(confidence)
        ):
            raise ContractError("defect fingerprint has conflicting triage evidence")
        cluster = clusters.setdefault(
            fingerprint,
            {
                "defect_id": "defect-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:20],
                "fingerprint": fingerprint,
                "failed_test_refs": [],
                "reproduction_descriptor_digest": reproduction_digest,
                "reproduction_execution_authorized": False,
                "root_cause_confidence": float(confidence),
            },
        )
        cluster["failed_test_refs"].append(test_id)
    if not failures:
        return {
            "state": "SUCCEEDED",
            "code": "NO_DEFECTS_TO_TRIAGE",
            "outputs": {"defects": [], "failure_count": 0},
        }
    return {
        "state": "PARTIAL",
        "code": "DEFECT_TRIAGE_PROPOSALS_CREATED",
        "outputs": {
            "defects": list(clusters.values()),
            "failure_count": len(failures),
            "reproduction_execution": "NOT_RUN",
        },
    }


def plan_repair(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    defect_id = require_resource_id(inputs.get("defect_id"), "defect_id")
    try:
        paths = [
            normalize_relative_path(path)
            for path in _strings(inputs.get("candidate_paths"), "candidate_paths")
        ]
    except ValueError as exc:
        raise ContractError("candidate_paths must be safe repository-relative paths") from exc
    if len(set(paths)) != len(paths):
        raise ContractError("candidate_paths may not contain duplicates")
    raw_tags = _strings(
        inputs.get("semantic_tags", []), "semantic_tags", allow_empty=True
    )
    _unique_casefold(raw_tags, "semantic_tags")
    semantic_tags = {value.casefold() for value in raw_tags}
    risk = _repair_risk(paths, semantic_tags)
    approval = "MULTI_ROLE_REQUIRED" if risk == "R3" else "CODE_OWNER_REQUIRED" if risk == "R2" else "POLICY_GATES_REQUIRED"
    plan_document = {
        "defect_id": defect_id,
        "risk_level": risk,
        "candidate_paths": sorted(set(paths)),
        "approval": approval,
    }
    return {
        "state": "SUCCEEDED",
        "code": "REPAIR_PLAN_CREATED",
        "outputs": {
            "repair_plan_id": "repair-" + digest_json(plan_document)[7:31],
            "repair_plan_digest": digest_json(plan_document),
            "repair_plan": plan_document,
            "defect_id": defect_id,
            "risk_level": risk,
            "candidate_paths": sorted(set(paths)),
            "approval": approval,
            "isolated_worktree_required": True,
            "full_regression_required": True,
        },
    }


def validate_patch(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    diff = require_exact_text(inputs.get("diff"), "diff", maximum=2_000_000)
    if "risk_level" in inputs:
        raise ContractError("risk_level is derived by policy and may not be caller-selected")
    raw_candidate_paths = _strings(inputs.get("candidate_paths"), "candidate_paths")
    try:
        candidate_paths = [
            normalize_relative_path(path)
            for path in raw_candidate_paths
        ]
    except ValueError as exc:
        raise ContractError("candidate_paths must be safe repository-relative paths") from exc
    if len(set(candidate_paths)) != len(candidate_paths):
        raise ContractError("candidate_paths may not contain duplicates")
    raw_semantic_tags = _strings(
        inputs.get("semantic_tags", []), "semantic_tags", allow_empty=True
    )
    _unique_casefold(raw_semantic_tags, "semantic_tags")
    semantic_tags = {value.casefold() for value in raw_semantic_tags}
    risk = _repair_risk(candidate_paths, semantic_tags)
    repair_plan_digest = _digest(inputs.get("repair_plan_digest"), "repair_plan_digest")
    repair_plan = inputs.get("repair_plan")
    if not isinstance(repair_plan, Mapping):
        raise ContractError("repair_plan must be the digest-bound planning document")
    if set(repair_plan) != {
        "defect_id",
        "risk_level",
        "candidate_paths",
        "approval",
    }:
        raise ContractError("repair_plan fields are incomplete or ambiguous")
    if digest_json(dict(repair_plan)) != repair_plan_digest:
        raise ContractError("repair_plan_digest does not match repair_plan")
    planned_paths = _strings(repair_plan.get("candidate_paths"), "repair_plan.candidate_paths")
    try:
        planned_paths = [normalize_relative_path(path) for path in planned_paths]
    except ValueError as exc:
        raise ContractError("repair_plan candidate paths are unsafe") from exc
    if tuple(sorted(planned_paths)) != tuple(sorted(candidate_paths)):
        raise ContractError("patch candidate paths differ from the repair plan")
    if repair_plan.get("risk_level") != risk:
        raise ContractError("patch risk differs from the repair plan")
    require_resource_id(repair_plan.get("defect_id"), "repair_plan.defect_id")
    require_text(repair_plan.get("approval"), "repair_plan.approval")
    lowered = diff.casefold()
    findings = sorted(marker for marker in FORBIDDEN_PATCH_MARKERS if marker in lowered)
    if re.search(r"\bassert\s+(?:true|1\s*==\s*1)\b", lowered):
        findings.append("obvious-tautology")
    diff_paths = _unified_diff_paths(diff)
    if diff_paths != tuple(sorted(candidate_paths)):
        findings.append("DIFF_PATHS_DO_NOT_MATCH_REPAIR_PLAN")
    isolated_value = inputs.get("isolated_worktree")
    sandboxed_value = inputs.get("sandboxed")
    if not isinstance(isolated_value, bool) or not isinstance(sandboxed_value, bool):
        raise ContractError("isolated_worktree and sandboxed must be booleans")
    isolated = isolated_value
    sandboxed = sandboxed_value
    approvals = _objects(inputs.get("approvals", []), "approvals", allow_empty=True)
    context = inputs.get("_runtime_context")
    actor_id = context.get("actor_id") if isinstance(context, Mapping) else None
    approved_roles: set[str] = set()
    approvers: set[str] = set()
    for approval in approvals:
        approver_id = require_resource_id(approval.get("approver_id"), "approver_id")
        role = require_text(approval.get("role"), "approval.role")
        bound_digest = _digest(
            approval.get("repair_plan_digest"), "approval.repair_plan_digest"
        )
        if bound_digest != repair_plan_digest:
            findings.append("APPROVAL_PLAN_DIGEST_MISMATCH")
        if actor_id is not None and approver_id == actor_id:
            findings.append("REPAIR_SELF_APPROVAL_FORBIDDEN")
        approvers.add(approver_id)
        approved_roles.add(role)
    if len(approvers) != len(approvals):
        findings.append("DUPLICATE_REPAIR_APPROVER")
    if risk == "R3" and not {"code-owner", "security-reviewer"}.issubset(approved_roles):
        findings.append("R3_APPROVALS_MISSING")
    if risk == "R2" and "code-owner" not in approved_roles:
        findings.append("R2_CODE_OWNER_APPROVAL_MISSING")
    if not isolated:
        findings.append("ISOLATED_WORKTREE_MISSING")
    if not sandboxed:
        findings.append("SANDBOX_ATTESTATION_MISSING")
    # Caller-provided booleans and approval objects are useful proposal data,
    # but they are not trusted execution or approval receipts.  This bounded
    # core therefore never authorizes patch application from them.
    findings.append("TRUSTED_REPAIR_RECEIPT_REQUIRED")
    return {
        "state": "BLOCKED",
        "code": "PATCH_REQUIRES_TRUSTED_EXECUTION_RECEIPT",
        "outputs": {
            "findings": sorted(set(findings)),
            "risk_level": risk,
            "repair_plan_digest": repair_plan_digest,
            "diff_paths": list(diff_paths),
            "execution_performed": False,
            "merge_authorized": False,
            "caller_approval_assertions_accepted": False,
            "caller_sandbox_assertions_accepted": False,
            "trusted_execution_receipt": "NOT_RUN",
            "diff_digest": digest_bytes(diff.encode()),
        },
        "implementation_state": "LOCAL_VALIDATED",
    }


def validate_test_heal(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    before = require_exact_text(inputs.get("before"), "before", maximum=1_000_000)
    after = require_exact_text(inputs.get("after"), "after", maximum=1_000_000)
    reason = require_text(inputs.get("reason"), "reason", maximum=1024)
    forbidden = []
    after_lower = after.casefold()
    if any(marker in after_lower for marker in FORBIDDEN_PATCH_MARKERS):
        forbidden.append("FORBIDDEN_TEST_PATTERN")
    if re.search(r"\bassert\s+(?:true|1\s*==\s*1)\b", after_lower):
        forbidden.append("OBVIOUS_TAUTOLOGY")
    before_assertions = before.casefold().count("assert") + before.casefold().count("expect(")
    after_assertions = after_lower.count("assert") + after_lower.count("expect(")
    if after_assertions < before_assertions:
        forbidden.append("ASSERTION_STRENGTH_DECREASED")
    semantic_change = inputs.get("business_oracle_changed") is True
    if not isinstance(inputs.get("business_oracle_changed", False), bool):
        raise ContractError("business_oracle_changed must be boolean")
    if semantic_change:
        forbidden.append("BUSINESS_ORACLE_CHANGED")
    # Text counting cannot establish behavioral equivalence.  A native parser,
    # isolated execution, independent oracle evidence, and a trusted approval
    # receipt are deliberately outside this bounded local operation.
    forbidden.append("TRUSTED_TEST_HEAL_RECEIPT_REQUIRED")
    return {
        "state": "BLOCKED",
        "code": "TEST_HEAL_REQUIRES_TRUSTED_EXECUTION_RECEIPT",
        "outputs": {
            "reason": reason,
            "findings": sorted(set(forbidden)),
            "before_digest": digest_bytes(before.encode()),
            "after_digest": digest_bytes(after.encode()),
            "execution_performed": False,
            "business_oracle_equivalence": "NOT_RUN",
            "trusted_execution_receipt": "NOT_RUN",
        },
        "implementation_state": "LOCAL_VALIDATED",
    }


def analyze_impact(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    from .gates import analyze_impact_contract

    return analyze_impact_contract(inputs)


def plan_advanced_testing(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    invariants = _unique(_strings(inputs.get("invariants"), "invariants"), "invariants")
    entrypoints = _unique(_strings(inputs.get("entrypoints"), "entrypoints"), "entrypoints")
    budget = inputs.get("budget_seconds")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        raise ContractError("budget_seconds must be a positive integer")
    quotient, remainder = divmod(budget, len(entrypoints))
    budgets = [quotient + (1 if index < remainder else 0) for index in range(len(entrypoints))]
    if any(value < 1 for value in budgets):
        raise ContractError("budget_seconds must allocate at least one second per entrypoint")
    return {
        "state": "SUCCEEDED",
        "code": "ADVANCED_TESTING_PLANNED",
        "outputs": {
            "property_cases": [{"invariant": value, "shrinking_required": True} for value in invariants],
            "fuzz_targets": [
                {
                    "entrypoint": value,
                    "bounded_seconds": budgets[index],
                    "corpus_persistence_required": True,
                    "corpus_persisted": False,
                }
                for index, value in enumerate(entrypoints)
            ],
            "total_bounded_seconds": sum(budgets),
            "mutation_baseline_required": True,
            "production_endpoints_allowed": False,
            "execution": "NOT_RUN",
            "adapter_binding_required": True,
        },
    }


def evaluate_quality_gate(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    from .gates import evaluate_quality_gate_contract

    return evaluate_quality_gate_contract(inputs)


def build_report(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    results = _objects(inputs.get("test_results", []), "test_results", allow_empty=True)
    counts: dict[str, int] = defaultdict(int)
    seen_result_ids: set[str] = set()
    for result in results:
        result_id = require_resource_id(result.get("test_case_id"), "test_case_id")
        if result_id in seen_result_ids:
            raise ContractError(f"duplicate test result: {result_id}")
        seen_result_ids.add(result_id)
        status = require_text(result.get("status"), "status").upper()
        if status not in TERMINAL_RESULTS | {"NOT_RUN", "UNKNOWN", "SKIPPED"}:
            raise ContractError("test result status is invalid")
        counts[status] += 1
    gate_report = inputs.get("gate_report")
    if not isinstance(gate_report, Mapping):
        raise ContractError("gate_report must be a digest-bound object")
    supplied_digest = _digest(gate_report.get("report_digest"), "gate_report.report_digest")
    unsigned_gate_report = dict(gate_report)
    unsigned_gate_report.pop("report_digest", None)
    if digest_json(unsigned_gate_report) != supplied_digest:
        raise ContractError("gate_report digest does not match its canonical content")
    gate = require_text(gate_report.get("decision"), "gate_report.decision")
    if gate not in {"FAILED", "BLOCKED", "READY_FOR_EXTERNAL_GATE"}:
        raise ContractError("gate_report.decision is invalid")
    if gate_report.get("certified") is not False:
        raise ContractError("local gate reports must explicitly remain uncertified")
    wall_clock = inputs.get("wall_clock_seconds", 0.0)
    human_equivalent = inputs.get("human_equivalent_seconds", 0.0)
    if (
        not isinstance(wall_clock, (int, float))
        or isinstance(wall_clock, bool)
        or not math.isfinite(float(wall_clock))
        or wall_clock < 0
        or not isinstance(human_equivalent, (int, float))
        or isinstance(human_equivalent, bool)
        or not math.isfinite(float(human_equivalent))
        or human_equivalent < 0
    ):
        raise ContractError("report durations must be non-negative numbers")
    report_body = {
        "gate_report_digest": supplied_digest,
        "gate_decision": gate,
        "test_status_counts": dict(sorted(counts.items())),
        "wall_clock_seconds": float(wall_clock),
        "human_equivalent_seconds": float(human_equivalent),
    }
    return {
        "state": "BLOCKED",
        "code": "TRUSTED_GATE_RECEIPT_REQUIRED",
        "outputs": {
            "summary": {"gate_decision": gate, "test_status_counts": dict(sorted(counts.items()))},
            "gate_report_digest": supplied_digest,
            "wall_clock_seconds": float(wall_clock),
            "human_equivalent_seconds": float(human_equivalent),
            "blocked_and_not_run_visible": True,
            "report_digest": digest_json(report_body),
            "certification": "NOT_CERTIFIED",
            "caller_gate_assertion_accepted": False,
            "trusted_gate_receipt": "NOT_RUN",
        },
    }


def create_checkpoint(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    run_id = require_resource_id(inputs.get("run_id"), "run_id")
    sequence = inputs.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ContractError("sequence must be a non-negative integer")
    state = inputs.get("state")
    if not isinstance(state, Mapping):
        raise ContractError("state must be an object")
    context = inputs.get("_runtime_context")
    if not isinstance(context, Mapping):
        raise ContractError("trusted runtime context is required")
    budget = inputs.get("budget_consumed", {})
    if not isinstance(budget, Mapping) or any(
        not isinstance(key, str)
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or value < 0
        for key, value in budget.items()
    ):
        raise ContractError("budget_consumed must map names to non-negative numbers")
    checkpoint = {
        "tenant_id": require_resource_id(context.get("tenant_id"), "runtime.tenant_id"),
        "project_id": require_resource_id(context.get("project_id"), "runtime.project_id"),
        "run_id": run_id,
        "sequence": sequence,
        "state": strict_json(state, "checkpoint.state"),
        "budget_consumed": strict_json(budget, "checkpoint.budget_consumed"),
        "idempotency_key": require_text(
            context.get("idempotency_key"), "runtime.idempotency_key", maximum=200
        ),
    }
    return {
        "state": "SUCCEEDED",
        "code": "CHECKPOINT_PROPOSAL_CREATED",
        "outputs": {
            "checkpoint_id": "checkpoint-" + digest_json(checkpoint)[7:31],
            "checkpoint": checkpoint,
            "fencing_token_required": True,
            "persisted": False,
            "durable_store_adapter": "NOT_RUN",
        },
    }


def estimate_eta(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    from .gates import estimate_eta_contract

    return estimate_eta_contract(inputs)


def adapter_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    adapters = _objects(inputs.get("adapters"), "adapters")
    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    required_methods = {"detect", "generate", "validate", "execute", "collect_coverage", "diagnose", "apply_patch"}
    shell_executables = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "pwsh"}
    for adapter in adapters:
        adapter_id = require_resource_id(adapter.get("adapter_id"), "adapter_id")
        methods = set(_strings(adapter.get("methods"), "adapter.methods"))
        commands = adapter.get("commands", [])
        if not isinstance(commands, list) or any(
            not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command)
            for command in commands
        ):
            raise ContractError("adapter commands must be structured argv arrays")
        if any(PurePosixPath(command[0]).name.casefold() in shell_executables for command in commands):
            raise ContractError("adapter commands may not invoke a shell interpreter")
        missing = sorted(required_methods - methods)
        if missing:
            blockers.append(f"{adapter_id}:MISSING:{','.join(missing)}")
        normalized.append({"adapter_id": adapter_id, "methods": sorted(methods), "commands": commands, "network": "DENY_BY_DEFAULT"})
    return {"state": "PARTIAL" if blockers else "SUCCEEDED", "code": "ADAPTER_CONTRACT_GAPS" if blockers else "ADAPTER_CONTRACTS_VALIDATED", "outputs": {"adapters": normalized, "blockers": blockers}}


def plan_ci(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    event = require_text(inputs.get("event"), "event")
    if event not in {"pull-request", "push", "nightly", "release", "manual"}:
        raise ContractError("CI event is invalid")
    try:
        changed = _unique(
            [
                normalize_relative_path(path)
                for path in _strings(
                    inputs.get("changed_nodes", []),
                    "changed_nodes",
                    allow_empty=True,
                )
            ],
            "changed_nodes",
        )
    except ValueError as exc:
        raise ContractError("changed_nodes must be safe repository-relative paths") from exc
    impact_report = inputs.get("impact_report")
    if not isinstance(impact_report, Mapping):
        raise ContractError("impact_report must be a digest-bound object")
    supplied_digest = _digest(
        impact_report.get("report_digest"), "impact_report.report_digest"
    )
    unsigned_report = dict(impact_report)
    unsigned_report.pop("report_digest", None)
    if digest_json(unsigned_report) != supplied_digest:
        raise ContractError("impact_report digest does not match its canonical content")
    full_regression = impact_report.get("full_regression_required")
    if not isinstance(full_regression, bool):
        raise ContractError("impact_report.full_regression_required must be boolean")
    # The caller can provide a content-consistent proposal but not an
    # authoritative impact receipt.  Until a repository-owned graph result is
    # bound, the conservative scope is always the full suite.
    scope = "FULL_REQUIRED"
    return {
        "state": "BLOCKED",
        "code": "TRUSTED_IMPACT_RECEIPT_REQUIRED",
        "outputs": {
            "event": event,
            "scope": scope,
            "changed_nodes": changed,
            "impact_report_digest": supplied_digest,
            "status_attestation_required": True,
            "quality_gate_changes_require_independent_approval": True,
            "merge_authorized": False,
            "caller_impact_assertion_accepted": False,
            "trusted_impact_receipt": "NOT_RUN",
        },
        "implementation_state": "LOCAL_VALIDATED",
    }


def propose_learning(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    source_state = require_text(inputs.get("source_state"), "source_state")
    rule = inputs.get("rule")
    if not isinstance(rule, Mapping):
        raise ContractError("rule must be an object")
    candidate = {
        "source_state": source_state,
        "rule": dict(rule),
    }
    if source_state != "CERTIFIED_EXTERNAL":
        code = "LEARNING_SOURCE_NOT_CERTIFIED"
    else:
        code = "TRUSTED_LEARNING_RECEIPT_REQUIRED"
    return {
        "state": "BLOCKED",
        "code": code,
        "outputs": {
            "candidate_digest": digest_json(candidate),
            "rule_digest": digest_json(rule),
            "caller_replay_assertion_accepted": False,
            "caller_approval_assertion_accepted": False,
            "candidate_persisted": False,
            "enabled": False,
            "rollback_required": True,
            "trusted_external_receipt": "NOT_RUN",
        },
    }


def authorize_action(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    context = inputs.get("_runtime_context")
    if not isinstance(context, Mapping):
        raise ContractError("trusted runtime context is required")
    actor_tenant = require_resource_id(context.get("tenant_id"), "runtime.tenant_id")
    actor_id = require_resource_id(context.get("actor_id"), "runtime.actor_id")
    resource_tenant = require_resource_id(inputs.get("resource_tenant_id"), "resource_tenant_id")
    action = require_text(inputs.get("action"), "action")
    role_values = _unique_casefold(
        _strings(inputs.get("roles", []), "roles", allow_empty=True), "roles"
    )
    required_role_values = _unique_casefold(
        _strings(
            inputs.get("required_roles", []), "required_roles", allow_empty=True
        ),
        "required_roles",
    )
    roles = {value.casefold() for value in role_values}
    required_roles = {value.casefold() for value in required_role_values}
    reasons = []
    if actor_tenant != resource_tenant:
        reasons.append("TENANT_MISMATCH")
    if not required_roles.issubset(roles):
        reasons.append("REQUIRED_ROLE_MISSING")
    if action in {"certify", "high-risk-repair", "legal-hold-release"}:
        reasons.append("INDEPENDENT_ACTOR_REQUIRED")
    if reasons:
        code = "AUTHORIZATION_DENIED"
    else:
        code = "TRUSTED_POLICY_DECISION_REQUIRED"
        reasons.append("CALLER_ROLES_ARE_NOT_AUTHORITY")
    return {
        "state": "BLOCKED",
        "code": code,
        "outputs": {
            "action": action,
            "actor_id": actor_id,
            "allowed": False,
            "local_role_match": required_roles.issubset(roles),
            "reasons": reasons,
            "audit_required": True,
            "trusted_policy_receipt": "NOT_RUN",
        },
    }


def plan_output(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    mode = require_text(inputs.get("run_mode"), "run_mode")
    output_mode = require_text(inputs.get("output_mode", "both"), "output_mode")
    if mode not in MODES or output_mode not in {"embedded", "sidecar", "both"}:
        raise ContractError("run or output mode is invalid")
    adapter = require_text(inputs.get("adapter"), "adapter")
    native_layout = require_text(inputs.get("native_layout"), "native_layout", maximum=1024)
    try:
        adapter_spec = adapter_for(adapter)
        normalized_layout = normalize_relative_path(native_layout)
    except (AdapterContractError, ValueError) as exc:
        raise ContractError("output adapter or native layout is invalid") from exc
    if not any(
        _layout_matches(pattern, normalized_layout)
        for pattern in adapter_spec.native_test_layouts
    ):
        raise ContractError("native layout is not matched by the exact adapter profile")
    bundles = [] if mode == "plan-only" else ["project-with-tests", "tests-only"]
    if mode in {"verify", "repair", "certify", "continuous"}:
        bundles.append("qa-evidence")
    if mode == "repair":
        bundles.append("repair-patches")
    return {"state": "SUCCEEDED", "code": "PROJECT_OUTPUT_PLANNED", "outputs": {"output_mode": output_mode, "adapter": adapter, "native_layout": normalized_layout, "required_bundles": bundles, "atomic_publish": True, "partial_on_failure": True}}


def plan_materialization(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    tests = _objects(inputs.get("test_cases"), "test_cases")
    adapter_key = require_text(inputs.get("adapter_key"), "adapter_key")
    raw_layout = require_text(inputs.get("native_layout"), "native_layout", maximum=1024)
    try:
        adapter = adapter_for(adapter_key)
        layout = normalize_relative_path(raw_layout)
    except (AdapterContractError, ValueError) as exc:
        raise ContractError("materialization adapter or layout is invalid") from exc
    if not any(_layout_matches(pattern, layout) for pattern in adapter.native_test_layouts):
        raise ContractError("native layout is not matched by the exact adapter profile")
    profile = MATERIALIZATION_PROFILES.get(adapter_key)
    if profile is None:
        return {
            "state": "BLOCKED",
            "code": "NATIVE_EMITTER_PROFILE_REQUIRED",
            "outputs": {
                "adapter_key": adapter_key,
                "native_layout": layout,
                "artifacts": [],
                "source_generation": "NOT_RUN",
            },
            "implementation_state": "LOCAL_VALIDATED",
        }
    prefix, suffix = profile
    paths: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_test_ids: set[str] = set()
    for test in tests:
        test_id = require_resource_id(test.get("test_case_id"), "test_case_id")
        if test_id in seen_test_ids:
            raise ContractError(f"duplicate test_case_id: {test_id}")
        seen_test_ids.add(test_id)
        stem = re.sub(r"[^A-Za-z0-9_]+", "_", test_id).strip("_")
        if not stem:
            stem = hashlib.sha256(test_id.encode("utf-8")).hexdigest()[:24]
        filename = f"{prefix}{stem[:80]}{suffix}"
        path = f"{layout}/{filename}"
        try:
            path = normalize_relative_path(path)
        except ValueError as exc:
            raise ContractError("materialization path is not portable") from exc
        folded = path.casefold()
        if folded in seen:
            raise ContractError("materialization path collision")
        seen.add(folded)
        paths.append(
            {
                "test_case_id": test_id,
                "path": path,
                "emitter_id": f"{adapter_key}:repository-owned-v1",
                "atomic_write": True,
                "manifest_required": True,
                "materialization_performed": False,
            }
        )
    return {
        "state": "SUCCEEDED",
        "code": "TEST_MATERIALIZATION_PLANNED",
        "outputs": {
            "adapter_key": adapter_key,
            "native_layout": layout,
            "artifacts": paths,
            "source_generation": "NOT_RUN",
            "validation_sequence": [
                "format",
                "syntax",
                "discover",
                "build",
                "smoke",
                "secret-scan",
            ],
        },
    }


def plan_bundles(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    artifacts = _objects(inputs.get("artifacts"), "artifacts")
    kinds = _unique(_strings(inputs.get("kinds"), "kinds"), "kinds")
    allowed = {"project-with-tests", "tests-only", "qa-evidence", "repair-patches"}
    if not set(kinds) <= allowed:
        raise ContractError("bundle kind is invalid")
    coverage = {
        "project-with-tests": {"project", "test"},
        "tests-only": {"test"},
        "qa-evidence": {"evidence", "coverage", "report", "log", "certificate"},
        "repair-patches": {"patch", "report", "evidence"},
    }
    required_categories = {
        "project-with-tests": {"project", "test"},
        "tests-only": {"test"},
        "qa-evidence": {"evidence", "report"},
        "repair-patches": {"patch"},
    }
    retained_categories = set().union(*(coverage[kind] for kind in kinds))
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    uncovered: list[str] = []
    for item in artifacts:
        artifact_id = require_resource_id(item.get("artifact_id"), "artifact_id")
        if artifact_id in seen_ids:
            raise ContractError(f"duplicate artifact_id: {artifact_id}")
        seen_ids.add(artifact_id)
        try:
            path = normalize_relative_path(item.get("path"))
        except (TypeError, ValueError) as exc:
            raise ContractError("artifact path must be safe and canonical") from exc
        collision = path.casefold()
        if collision in seen_paths:
            raise ContractError("artifact paths collide on a portable filesystem")
        seen_paths.add(collision)
        digest = _digest(item.get("sha256"), "artifact.sha256")
        category = require_text(item.get("category"), "artifact.category")
        if category not in ARTIFACT_CATEGORIES:
            raise ContractError("artifact category is invalid")
        if category not in retained_categories:
            uncovered.append(artifact_id)
        normalized.append(
            {
                "artifact_id": artifact_id,
                "path": path,
                "sha256": digest,
                "category": category,
            }
        )
    observed_categories = {record["category"] for record in normalized}
    missing_bundle_categories = {
        kind: sorted(required_categories[kind] - observed_categories)
        for kind in kinds
        if required_categories[kind] - observed_categories
    }
    proposal = {"kinds": kinds, "artifacts": sorted(normalized, key=lambda row: row["artifact_id"])}
    return {
        "state": "BLOCKED" if uncovered or missing_bundle_categories else "SUCCEEDED",
        "code": "ARTIFACTS_NOT_RETAINED"
        if uncovered
        else "BUNDLE_CONTENT_INCOMPLETE"
        if missing_bundle_categories
        else "BUNDLE_PUBLICATION_PLANNED",
        "outputs": {
            "kinds": kinds,
            "artifact_count": len(artifacts),
            "unretained_artifact_ids": sorted(uncovered),
            "missing_bundle_categories": missing_bundle_categories,
            "manifest_proposal": proposal,
            "manifest_proposal_digest": digest_json(proposal),
            "deterministic_order": True,
            "extract_and_verify": True,
            "atomic_publish": True,
            "publication_performed": False,
            "signing": "NOT_RUN",
        },
    }


def evaluate_lifecycle(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    artifacts = _objects(inputs.get("artifacts"), "artifacts")
    referenced_values = [
        require_resource_id(value, "referenced_artifact_ids[]")
        for value in _strings(
            inputs.get("referenced_artifact_ids", []),
            "referenced_artifact_ids",
            allow_empty=True,
        )
    ]
    hold_values = [
        require_resource_id(value, "legal_hold_artifact_ids[]")
        for value in _strings(
            inputs.get("legal_hold_artifact_ids", []),
            "legal_hold_artifact_ids",
            allow_empty=True,
        )
    ]
    referenced = set(_unique(referenced_values, "referenced_artifact_ids"))
    holds = set(_unique(hold_values, "legal_hold_artifact_ids"))
    stale_inputs = set(
        _unique(
            _strings(
                inputs.get("changed_input_refs", []),
                "changed_input_refs",
                allow_empty=True,
            ),
            "changed_input_refs",
        )
    )
    stale: list[str] = []
    gc_candidates: list[str] = []
    artifact_by_id: dict[str, Mapping[str, Any]] = {}
    for artifact in artifacts:
        artifact_id = require_resource_id(artifact.get("artifact_id"), "artifact_id")
        if artifact_id in artifact_by_id:
            raise ContractError(f"duplicate artifact_id: {artifact_id}")
        artifact_by_id[artifact_id] = artifact
        source_refs = set(_strings(artifact.get("source_refs", []), "source_refs", allow_empty=True))
        superseded = artifact.get("superseded", False)
        required = artifact.get("required", False)
        if not isinstance(superseded, bool) or not isinstance(required, bool):
            raise ContractError("artifact required and superseded must be booleans")
        if source_refs & stale_inputs:
            stale.append(artifact_id)
        if (
            superseded
            and not required
            and artifact_id not in referenced
            and artifact_id not in holds
        ):
            gc_candidates.append(artifact_id)
    unknown_refs = sorted((referenced | holds) - set(artifact_by_id))
    if unknown_refs:
        raise ContractError(f"lifecycle references unknown artifacts: {unknown_refs}")
    required_stale = [
        item for item in stale if artifact_by_id[item].get("required") is True
    ]
    return {
        "state": "PARTIAL" if required_stale else "SUCCEEDED",
        "code": "REQUIRED_ARTIFACTS_STALE"
        if required_stale
        else "OUTPUT_LIFECYCLE_EVALUATED",
        "outputs": {
            "stale_artifact_ids": stale,
            "required_stale_artifact_ids": required_stale,
            "gc_candidates": gc_candidates,
            "two_phase_gc_required": True,
            "deletion_performed": False,
        },
    }
