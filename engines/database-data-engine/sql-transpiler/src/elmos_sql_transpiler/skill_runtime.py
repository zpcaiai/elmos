"""Executable, fail-closed runtime for the 47 ChinaDB migration Skills.

The imported ChinaDB package is immutable specification material.  This
module is repository-owned product code: every exact Skill identity is bound
to a concrete local handler, while database/provider effects remain behind an
explicit external boundary.  A local result never manufactures target
execution, independent verification, or certification evidence.

The handlers deliberately consume typed JSON contracts rather than paths,
shell commands, credentials, or raw provider connections.  This keeps local
assessment deterministic and makes it possible to test every Skill without
granting production authority.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Literal, NoReturn

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, TokenError

from .commercial import assess_commercial, commercial_capabilities
from .commercial_request import parse_commercial_request_json
from .profiles import profile_by_id
from .transpiler import _require_pinned_parser

PACKAGE = "chinadb-commercial-migration-skills"
RUNTIME_VERSION = "1.0.0"
MAX_REQUEST_BYTES = 1_048_576
MAX_COLLECTION_ITEMS = 2_000
MAX_DEPTH = 20

LocalState = Literal[
    "LOCAL_COMPLETED",
    "LOCAL_FAILED",
    "BLOCKED_EXTERNAL",
    "READY_FOR_HUMAN_DECISION",
    "READY_FOR_EXTERNAL_GATE",
]

_SCOPE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "accesstoken",
        "accesskey",
        "privatekey",
        "connectionstring",
        "dsn",
    }
)
_STABLE_ERRORS = frozenset(
    {
        "duplicate_key",
        "foreign_key_violation",
        "check_violation",
        "not_null_violation",
        "numeric_overflow",
        "deadlock",
        "serialization_failure",
        "lock_timeout",
        "statement_timeout",
        "connection_failure",
        "permission_denied",
        "object_not_found",
        "syntax_or_feature_unsupported",
    }
)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Skill payload must be finite canonical JSON") from error


def _reject_non_finite_constant(value: str) -> NoReturn:
    raise ValueError(f"Skill payload contains prohibited non-finite number {value}")


def _object_without_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Skill payload contains duplicate field {key!r}")
        result[key] = value
    return result


def parse_skill_request_json(
    payload: bytes,
    *,
    maximum: int = MAX_REQUEST_BYTES,
) -> dict[str, Any]:
    """Decode one strict bounded JSON Skill request without duplicate fields."""

    if len(payload) > maximum:
        raise ValueError(f"Skill payload exceeds the {maximum} byte input limit")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Skill payload must be valid UTF-8 JSON") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_fields,
            parse_constant=_reject_non_finite_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError("Skill payload must be valid JSON") from error
    return _object(value, "payload")


def _digest_value(value: Any) -> str:
    return "sha256:" + sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _digest_text(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a JSON object with string keys")
    return {str(key): child for key, child in value.items()}


def _objects(
    value: object, name: str, *, maximum: int = MAX_COLLECTION_ITEMS
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds the {maximum} item limit")
    return [_object(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _strings(value: object, name: str, *, maximum: int = MAX_COLLECTION_ITEMS) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds the {maximum} item limit")
    return list(value)


def _required_string(
    value: object,
    name: str,
    *,
    pattern: re.Pattern[str] | None = None,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must be a non-empty string of at most {maximum} characters")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ValueError(f"{name} has an invalid format")
    return value


def _required_digest(value: object, name: str) -> str:
    return _required_string(value, name, pattern=_DIGEST)


def _walk_request(value: object, *, depth: int = 0, key: str | None = None) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("Skill payload exceeds the maximum nesting depth")
    if key is not None:
        normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
        if normalized in _FORBIDDEN_SECRET_KEYS:
            raise ValueError(
                f"inline secret field {key!r} is prohibited; use an opaque credentialRef"
            )
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("Skill payload object exceeds the item limit")
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise ValueError("Skill payload object keys must be strings")
            _walk_request(child, depth=depth + 1, key=child_key)
    elif isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("Skill payload array exceeds the item limit")
        for child in value:
            _walk_request(child, depth=depth + 1)
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise ValueError("Skill payload contains a non-JSON value")


def _validate_scope(payload: Mapping[str, Any]) -> dict[str, str]:
    scope = _object(payload.get("scope"), "scope")
    result: dict[str, str] = {}
    for field in ("tenantId", "projectId", "actorId"):
        result[field] = _required_string(scope.get(field), f"scope.{field}", pattern=_SCOPE_TOKEN)
    if set(scope) != set(result):
        raise ValueError("scope accepts exactly tenantId, projectId, and actorId")
    return result


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    handler_id: str
    category: str
    dependencies: tuple[str, ...] = ()
    external_effects: tuple[str, ...] = ()
    bound_value: str | None = None

    @property
    def alias(self) -> str:
        return f"chinadb-{self.skill_id}"


@dataclass(frozen=True)
class HandlerOutcome:
    state: LocalState
    artifacts: Mapping[str, Any]
    blockers: tuple[Mapping[str, Any], ...] = ()
    checks: tuple[Mapping[str, Any], ...] = ()


def _blocker(code: str, message: str, *, severity: str = "ERROR") -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


_TARGET_BINDINGS = {
    "40-target-dm8": "dm8",
    "41-target-kingbasees": "kingbasees",
    "42-target-opengauss": "opengauss",
    "43-target-tidb": "tidb",
    "44-target-gbase8s": "gbase-8s",
    "45-target-gbase8c": "gbase-8c",
    "46-target-gbase8a": "gbase-8a",
    "47-target-highgo": "highgo-hgdb",
    "48-target-oceanbase-oracle": "oceanbase-oracle",
    "49-target-oceanbase-mysql": "oceanbase-mysql",
    "50-target-gaussdb-oracle": "gaussdb-oracle",
    "51-target-gaussdb-m": "gaussdb-m",
    "52-target-goldendb": "goldendb",
}

_SOURCE_BINDINGS = {
    "20-source-oracle-adapter": "oracle-26ai-ee",
    "21-source-sqlserver-adapter": "sqlserver-2022-cu26",
    "22-source-postgresql-adapter": "postgresql-17.5",
    "23-source-mysql-adapter": "mysql-8.4.10-lts",
    "24-source-db2-adapter": "db2-luw",
    "25-source-sybase-adapter": "sybase-ase",
}

_APP_BINDINGS = {
    "30-app-java-spring-adapter": "java-spring",
    "31-app-dotnet-adapter": "dotnet",
    "32-app-python-adapter": "python",
    "33-app-nodejs-adapter": "nodejs",
    "34-app-go-adapter": "go",
}


def _specs() -> tuple[SkillSpec, ...]:
    core = (
        SkillSpec("00-migration-program-orchestrator", "orchestrate", "orchestration"),
        SkillSpec("01-estate-inventory-assessment", "inventory", "discovery"),
        SkillSpec(
            "02-semantic-db-ir", "semantic-ir", "canonical-ir", ("01-estate-inventory-assessment",)
        ),
        SkillSpec("03-rule-mutation-dsl", "rule-dsl", "transformation", ("02-semantic-db-ir",)),
        SkillSpec(
            "04-data-movement-cdc",
            "cdc-plan",
            "data-movement",
            ("01-estate-inventory-assessment", "02-semantic-db-ir"),
            ("source-read", "target-write", "cdc"),
        ),
        SkillSpec(
            "05-ddl-auto-conversion",
            "ddl-conversion",
            "conversion",
            ("02-semantic-db-ir", "03-rule-mutation-dsl"),
        ),
        SkillSpec(
            "06-sql-auto-conversion",
            "sql-conversion",
            "conversion",
            ("02-semantic-db-ir", "03-rule-mutation-dsl"),
        ),
        SkillSpec(
            "07-plsql-tsql-conversion", "procedural-strategy", "procedural", ("02-semantic-db-ir",)
        ),
        SkillSpec(
            "08-application-code-auto-refactor",
            "application-plan",
            "application",
            ("06-sql-auto-conversion", "07-plsql-tsql-conversion"),
            ("repository-write",),
        ),
        SkillSpec(
            "09-behavior-equivalence-verification",
            "behavior-verify",
            "verification",
            ("05-ddl-auto-conversion", "06-sql-auto-conversion"),
            ("source-read", "target-read"),
        ),
        SkillSpec(
            "10-performance-equivalence-verification",
            "performance-verify",
            "verification",
            ("09-behavior-equivalence-verification",),
            ("source-read", "target-read"),
        ),
        SkillSpec(
            "11-guarded-auto-repair",
            "repair-plan",
            "repair",
            ("09-behavior-equivalence-verification", "10-performance-equivalence-verification"),
            ("repository-write", "target-write"),
        ),
        SkillSpec(
            "12-cutover-rollback",
            "cutover-gate",
            "cutover",
            (
                "04-data-movement-cdc",
                "09-behavior-equivalence-verification",
                "10-performance-equivalence-verification",
            ),
            ("production-switch", "target-write"),
        ),
        SkillSpec(
            "13-production-migration-certification",
            "certification-gate",
            "certification",
            ("12-cutover-rollback", "14-security-governance", "15-evidence-ledger-reproducibility"),
        ),
        SkillSpec(
            "14-security-governance",
            "security-diff",
            "security",
            ("02-semantic-db-ir",),
            ("identity-read", "target-write"),
        ),
        SkillSpec("15-evidence-ledger-reproducibility", "evidence-ledger", "evidence"),
        SkillSpec(
            "16-release-ci-quality-gates",
            "release-gate",
            "release",
            ("13-production-migration-certification", "15-evidence-ledger-reproducibility"),
        ),
    )
    sources = tuple(
        SkillSpec(
            skill_id,
            f"source:{profile}",
            "source-adapter",
            ("01-estate-inventory-assessment", "02-semantic-db-ir"),
            ("source-read",),
            profile,
        )
        for skill_id, profile in _SOURCE_BINDINGS.items()
    )
    apps = tuple(
        SkillSpec(
            skill_id,
            f"application:{language}",
            "application-adapter",
            ("08-application-code-auto-refactor",),
            ("repository-write",),
            language,
        )
        for skill_id, language in _APP_BINDINGS.items()
    )
    targets = tuple(
        SkillSpec(
            skill_id,
            f"target:{target_id}",
            "target-adapter",
            ("02-semantic-db-ir", "03-rule-mutation-dsl"),
            ("target-read", "target-write", "provider-call"),
            target_id,
        )
        for skill_id, target_id in _TARGET_BINDINGS.items()
    )
    support = (
        SkillSpec(
            "60-route-support-matrix",
            "route-matrix",
            "control-plane",
            ("15-evidence-ledger-reproducibility",),
        ),
        SkillSpec(
            "61-fixture-corpus-and-mutation-tests",
            "mutation-gate",
            "testing",
            ("09-behavior-equivalence-verification",),
        ),
        SkillSpec(
            "62-benchmark-lab",
            "benchmark-gate",
            "testing",
            ("10-performance-equivalence-verification",),
            ("source-read", "target-read"),
        ),
        SkillSpec(
            "63-migration-estimation-commercial-report",
            "estimate",
            "reporting",
            ("01-estate-inventory-assessment", "60-route-support-matrix"),
        ),
        SkillSpec(
            "64-vendor-native-tool-bridge",
            "vendor-bridge",
            "provider-bridge",
            ("04-data-movement-cdc", "05-ddl-auto-conversion"),
            ("provider-call", "target-write"),
        ),
        SkillSpec(
            "65-observability-migration-control-plane",
            "observability",
            "control-plane",
            (
                "12-cutover-rollback",
                "15-evidence-ledger-reproducibility",
                "60-route-support-matrix",
            ),
        ),
    )
    return core + sources + apps + targets + support


SKILL_SPECS = _specs()
SKILLS_BY_ID = {spec.skill_id: spec for spec in SKILL_SPECS}

if len(SKILL_SPECS) != 47 or len(SKILLS_BY_ID) != 47:
    raise RuntimeError("ChinaDB runtime must bind exactly 47 unique Skill identities")


def _topological_plan(requested: Sequence[str]) -> list[str]:
    closure: set[str] = set()

    def include(skill_id: str) -> None:
        if skill_id not in SKILLS_BY_ID:
            raise ValueError(f"unknown ChinaDB Skill id: {skill_id}")
        if skill_id in closure:
            return
        for dependency in SKILLS_BY_ID[skill_id].dependencies:
            include(dependency)
        closure.add(skill_id)

    for skill_id in requested:
        include(skill_id)
    remaining = set(closure)
    ordered: list[str] = []
    while remaining:
        ready = sorted(
            item for item in remaining if set(SKILLS_BY_ID[item].dependencies).isdisjoint(remaining)
        )
        if not ready:
            raise RuntimeError("ChinaDB Skill dependency graph contains a cycle")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def _handle_orchestrator(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    requested = _strings(payload.get("requestedSkills"), "requestedSkills", maximum=47)
    if not requested:
        raise ValueError("requestedSkills must not be empty")
    ordered = _topological_plan(requested)
    return HandlerOutcome(
        state="LOCAL_COMPLETED",
        artifacts={
            "requestedSkills": requested,
            "dependencyClosedPlan": ordered,
            "steps": [
                {
                    "skillId": skill_id,
                    "handlerId": SKILLS_BY_ID[skill_id].handler_id,
                    "externalEffects": list(SKILLS_BY_ID[skill_id].external_effects),
                }
                for skill_id in ordered
            ],
        },
        checks=({"id": "DEPENDENCY_CLOSED", "state": "PASSED"},),
    )


def _handle_inventory(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    objects = _objects(payload.get("objects"), "objects")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    kinds: Counter[str] = Counter()
    unsupported = 0
    for index, item in enumerate(objects):
        object_id = _required_string(
            item.get("objectId"), f"objects[{index}].objectId", pattern=_SAFE_ID
        )
        if object_id in seen:
            raise ValueError(f"duplicate inventory objectId: {object_id}")
        seen.add(object_id)
        kind = _required_string(
            item.get("kind"), f"objects[{index}].kind", pattern=_SAFE_ID
        ).upper()
        definition_digest = _required_digest(
            item.get("definitionDigest"), f"objects[{index}].definitionDigest"
        )
        dependencies = _strings(item.get("dependencies", []), f"objects[{index}].dependencies")
        support = str(item.get("support", "UNKNOWN")).upper()
        if support not in {"SUPPORTED", "CONDITIONAL", "UNSUPPORTED", "UNKNOWN"}:
            raise ValueError(f"objects[{index}].support is invalid")
        unsupported += support in {"UNSUPPORTED", "UNKNOWN"}
        kinds[kind] += 1
        normalized.append(
            {
                "objectId": object_id,
                "kind": kind,
                "definitionDigest": definition_digest,
                "dependencies": sorted(dependencies),
                "support": support,
            }
        )
    missing_dependencies = sorted(
        {
            dependency
            for item in normalized
            for dependency in item["dependencies"]
            if dependency not in seen
        }
    )
    blockers: tuple[Mapping[str, Any], ...] = ()
    if missing_dependencies:
        blockers = (
            _blocker(
                "INVENTORY_DEPENDENCY_MISSING",
                "Inventory references objects that were not supplied.",
            ),
        )
    return HandlerOutcome(
        state="LOCAL_FAILED" if blockers else "LOCAL_COMPLETED",
        artifacts={
            "objects": sorted(normalized, key=lambda item: item["objectId"]),
            "objectCount": len(normalized),
            "kindCounts": dict(sorted(kinds.items())),
            "unsupportedOrUnknown": unsupported,
            "missingDependencies": missing_dependencies,
            "inventoryDigest": _digest_value(normalized),
        },
        blockers=blockers,
    )


def _handle_semantic_ir(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    nodes = _objects(payload.get("nodes"), "nodes")
    identities: set[str] = set()
    normalized: list[dict[str, Any]] = []
    unsupported_count = 0
    for index, item in enumerate(nodes):
        node_id = _required_string(item.get("id"), f"nodes[{index}].id", pattern=_SAFE_ID)
        if node_id in identities:
            raise ValueError(f"duplicate canonical node id: {node_id}")
        identities.add(node_id)
        kind = _required_string(item.get("kind"), f"nodes[{index}].kind", pattern=_SAFE_ID).upper()
        source_digest = _required_digest(item.get("sourceDigest"), f"nodes[{index}].sourceDigest")
        semantics = _object(item.get("semantics"), f"nodes[{index}].semantics")
        dependencies = _strings(item.get("dependencies", []), f"nodes[{index}].dependencies")
        unsupported_extensions = _objects(
            item.get("unsupportedExtensions", []), f"nodes[{index}].unsupportedExtensions"
        )
        for extension_index, extension in enumerate(unsupported_extensions):
            _required_string(
                extension.get("provider"),
                f"nodes[{index}].unsupportedExtensions[{extension_index}].provider",
                pattern=_SAFE_ID,
            )
            _required_string(
                extension.get("code"),
                f"nodes[{index}].unsupportedExtensions[{extension_index}].code",
                pattern=_SAFE_ID,
            )
        unsupported_count += len(unsupported_extensions)
        normalized.append(
            {
                "id": node_id,
                "kind": kind,
                "sourceDigest": source_digest,
                "semantics": semantics,
                "dependencies": sorted(dependencies),
                "unsupportedExtensions": unsupported_extensions,
            }
        )
    missing = sorted(
        {
            dependency
            for node in normalized
            for dependency in node["dependencies"]
            if dependency not in identities
        }
    )
    blockers = (
        ()
        if not missing
        else (
            _blocker(
                "CANONICAL_IR_REFERENCE_MISSING",
                "Canonical IR contains unresolved dependency references.",
            ),
        )
    )
    return HandlerOutcome(
        state="LOCAL_FAILED" if blockers else "LOCAL_COMPLETED",
        artifacts={
            "schemaVersion": "1.0",
            "nodes": sorted(normalized, key=lambda item: item["id"]),
            "nodeCount": len(normalized),
            "unsupportedExtensionCount": unsupported_count,
            "unresolvedReferences": missing,
            "modelDigest": _digest_value(normalized),
        },
        blockers=blockers,
    )


_RULE_ACTIONS = frozenset(
    {"NATIVE", "REWRITE", "LIFT_TO_APP", "EMULATE_WITH_APPROVAL", "UNSUPPORTED"}
)


def _handle_rule_dsl(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    rules = _objects(payload.get("rules"), "rules")
    compiled: list[dict[str, Any]] = []
    ids: set[str] = set()
    slots: dict[tuple[str, int, str], str] = {}
    conflicts: list[str] = []
    for index, rule in enumerate(rules):
        rule_id = _required_string(rule.get("ruleId"), f"rules[{index}].ruleId", pattern=_SAFE_ID)
        if rule_id in ids:
            raise ValueError(f"duplicate conversion ruleId: {rule_id}")
        ids.add(rule_id)
        source_kind = _required_string(
            rule.get("sourceKind"), f"rules[{index}].sourceKind", pattern=_SAFE_ID
        ).upper()
        predicate = _object(rule.get("predicate"), f"rules[{index}].predicate")
        action = _required_string(rule.get("action"), f"rules[{index}].action").upper()
        if action not in _RULE_ACTIONS:
            raise ValueError(f"rules[{index}].action is invalid")
        priority = rule.get("priority", 100)
        if not isinstance(priority, int) or priority < 0 or priority > 10_000:
            raise ValueError(f"rules[{index}].priority is invalid")
        risk = str(rule.get("risk", "MEDIUM")).upper()
        if risk not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError(f"rules[{index}].risk is invalid")
        predicate_digest = _digest_value(predicate)
        slot = (source_kind, priority, predicate_digest)
        previous = slots.get(slot)
        if previous is not None and previous != action:
            conflicts.extend([rule_id])
        slots[slot] = action
        compiled.append(
            {
                "ruleId": rule_id,
                "sourceKind": source_kind,
                "predicate": predicate,
                "predicateDigest": predicate_digest,
                "action": action,
                "priority": priority,
                "risk": risk,
                "approvalRequired": action == "EMULATE_WITH_APPROVAL"
                or risk in {"HIGH", "CRITICAL"},
            }
        )
    compiled.sort(key=lambda item: (item["priority"], item["ruleId"]))
    blockers = (
        ()
        if not conflicts
        else (
            _blocker(
                "RULE_COLLISION",
                "Two rules claim the same predicate and priority with different actions.",
            ),
        )
    )
    return HandlerOutcome(
        state="LOCAL_FAILED" if blockers else "LOCAL_COMPLETED",
        artifacts={
            "rules": compiled,
            "ruleCount": len(compiled),
            "conflictingRuleIds": sorted(set(conflicts)),
            "rulePackDigest": _digest_value(compiled),
        },
        blockers=blockers,
    )


def _handle_cdc(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    snapshot_digest = _required_digest(payload.get("sourceSnapshotDigest"), "sourceSnapshotDigest")
    chunks = _objects(payload.get("chunks"), "chunks")
    events = _objects(payload.get("cdcEvents", []), "cdcEvents")
    source_rows = _strings(payload.get("sourceRowDigests", []), "sourceRowDigests")
    target_rows = _strings(payload.get("targetRowDigests", []), "targetRowDigests")
    chunk_ids: set[str] = set()
    normalized_chunks: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        chunk_id = _required_string(
            chunk.get("chunkId"), f"chunks[{index}].chunkId", pattern=_SAFE_ID
        )
        if chunk_id in chunk_ids:
            raise ValueError(f"duplicate CDC chunkId: {chunk_id}")
        chunk_ids.add(chunk_id)
        start = chunk.get("start")
        end = chunk.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
            raise ValueError(f"chunks[{index}] has an invalid bounded range")
        normalized_chunks.append(
            {
                "chunkId": chunk_id,
                "start": start,
                "end": end,
                "payloadDigest": _required_digest(
                    chunk.get("payloadDigest"), f"chunks[{index}].payloadDigest"
                ),
            }
        )
    event_ids: set[str] = set()
    positions: list[int] = []
    duplicate_events: list[str] = []
    for index, event in enumerate(events):
        event_id = _required_string(
            event.get("eventId"), f"cdcEvents[{index}].eventId", pattern=_SAFE_ID
        )
        position = event.get("position")
        if not isinstance(position, int) or position < 0:
            raise ValueError(f"cdcEvents[{index}].position is invalid")
        if event_id in event_ids:
            duplicate_events.append(event_id)
        event_ids.add(event_id)
        positions.append(position)
    out_of_order = any(right <= left for left, right in zip(positions, positions[1:], strict=False))
    source_counter = Counter(source_rows)
    target_counter = Counter(target_rows)
    missing_rows = sorted((source_counter - target_counter).elements())
    extra_rows = sorted((target_counter - source_counter).elements())
    blockers: list[Mapping[str, Any]] = []
    if duplicate_events:
        blockers.append(_blocker("CDC_DUPLICATE_EVENT", "CDC event identities are not unique."))
    if out_of_order:
        blockers.append(
            _blocker("CDC_POSITION_NOT_MONOTONIC", "CDC positions are not strictly increasing.")
        )
    if missing_rows or extra_rows:
        blockers.append(
            _blocker("DETAIL_RECONCILIATION_MISMATCH", "Source and target row digests differ.")
        )
    blockers.append(
        _blocker(
            "EXTERNAL_DATA_MOVEMENT_NOT_RUN",
            (
                "The bounded local plan does not authorize source reads, target writes, "
                "or CDC startup."
            ),
            severity="INFO",
        )
    )
    return HandlerOutcome(
        state="BLOCKED_EXTERNAL",
        artifacts={
            "sourceSnapshotDigest": snapshot_digest,
            "chunks": sorted(normalized_chunks, key=lambda item: item["start"]),
            "checkpoint": max(positions) if positions else None,
            "eventCount": len(events),
            "duplicateEventIds": sorted(set(duplicate_events)),
            "missingTargetRowDigests": missing_rows,
            "extraTargetRowDigests": extra_rows,
            "reconciliationPassed": not missing_rows and not extra_rows,
            "movementPlanDigest": _digest_value(
                {"snapshot": snapshot_digest, "chunks": normalized_chunks}
            ),
        },
        blockers=tuple(blockers),
    )


_DDL_KINDS = frozenset({"CREATE", "ALTER", "DROP", "COMMENT", "GRANT", "REVOKE", "TRUNCATE"})


def _handle_conversion(payload: Mapping[str, Any], spec: SkillSpec) -> HandlerOutcome:
    request = _object(payload.get("assessment"), "assessment")
    parsed_request = parse_commercial_request_json(
        (_canonical_json(request) + "\n").encode("utf-8")
    )
    assessment = assess_commercial(parsed_request).to_dict()
    kinds = {str(item.get("kind", "")).upper() for item in assessment["statements"]}
    if spec.skill_id == "05-ddl-auto-conversion":
        wrong = sorted(kind for kind in kinds if kind not in _DDL_KINDS)
        expected = "DDL"
    else:
        wrong = sorted(kind for kind in kinds if kind in _DDL_KINDS)
        expected = "query/DML"
    blockers = list(assessment["blockers"])
    if wrong:
        blockers.append(
            _blocker(
                "SKILL_STATEMENT_KIND_MISMATCH",
                (
                    f"{spec.skill_id} accepts {expected} statements; mismatched kinds: "
                    f"{', '.join(wrong)}"
                ),
            )
        )
    assessment["blockers"] = blockers
    return HandlerOutcome(
        state="BLOCKED_EXTERNAL",
        artifacts={
            "assessment": assessment,
            "typedStatementCount": len(assessment["statements"]),
            "targetSql": None,
        },
        blockers=tuple(blockers),
        checks=(
            {
                "id": "SOURCE_TYPED_PARSE",
                "state": assessment["verification"]["sourceParse"],
            },
            {"id": "TARGET_SQL_NOT_FABRICATED", "state": "PASSED"},
        ),
    )


def _handle_procedural(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    units = _objects(payload.get("units"), "units")
    strategies: list[dict[str, Any]] = []
    blocked = 0
    for index, unit in enumerate(units):
        unit_id = _required_string(unit.get("unitId"), f"units[{index}].unitId", pattern=_SAFE_ID)
        language = _required_string(
            unit.get("language"), f"units[{index}].language", pattern=_SAFE_ID
        ).upper()
        flags = {
            key: bool(unit.get(key, False))
            for key in (
                "dynamicSql",
                "packageState",
                "autonomousTransaction",
                "transactionControl",
                "securityDefiner",
                "sideEffects",
                "exceptionFlow",
                "cursorFlow",
            )
        }
        typed_signature = bool(unit.get("typedSignature", False))
        if flags["dynamicSql"] or flags["autonomousTransaction"]:
            strategy = "UNSUPPORTED"
            reason = "runtime-dependent SQL or autonomous transaction semantics require redesign"
            blocked += 1
        elif flags["packageState"] or flags["transactionControl"] or flags["securityDefiner"]:
            strategy = "LIFT_TO_APP"
            reason = (
                "state, transaction, or security context requires an explicit application contract"
            )
        elif typed_signature and not any(flags.values()):
            strategy = "DIRECT_TARGET_CANDIDATE"
            reason = "typed, deterministic, side-effect-free unit"
        elif typed_signature:
            strategy = "REWRITE"
            reason = "typed procedural unit requires target control-flow and side-effect validation"
        else:
            strategy = "UNSUPPORTED"
            reason = "routine signature or effects are not fully typed"
            blocked += 1
        strategies.append(
            {
                "unitId": unit_id,
                "language": language,
                "strategy": strategy,
                "reason": reason,
                "flags": flags,
                "verificationPath": [
                    "TARGET_COMPILE",
                    "RESULT_AND_OUT_VALUE_DIFF",
                    "SIDE_EFFECT_DIFF",
                    "ERROR_AND_ROLLBACK_DIFF",
                ],
            }
        )
    blockers = (
        ()
        if blocked == 0
        else (
            _blocker(
                "PROCEDURAL_UNIT_UNSUPPORTED",
                f"{blocked} procedural units require manual redesign.",
            ),
        )
    )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "strategies": strategies,
            "unitCount": len(strategies),
            "blockedUnitCount": blocked,
            "strategyDigest": _digest_value(strategies),
        },
        blockers=blockers,
    )


def _app_patch_plan(payload: Mapping[str, Any], language: str | None) -> HandlerOutcome:
    call_sites = _objects(payload.get("callSites"), "callSites")
    target_driver = _required_string(payload.get("targetDriver"), "targetDriver", pattern=_SAFE_ID)
    plans: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for index, site in enumerate(call_sites):
        call_id = _required_string(
            site.get("callId"), f"callSites[{index}].callId", pattern=_SAFE_ID
        )
        site_language = _required_string(
            site.get("language"), f"callSites[{index}].language", pattern=_SAFE_ID
        ).casefold()
        if language is not None and site_language.replace(".", "") not in {
            language.replace("-spring", "").replace(".", ""),
            language.replace(".", ""),
        }:
            unresolved.append(call_id)
            continue
        parameterized = bool(site.get("parameterized", False))
        transaction_known = bool(site.get("transactionKnown", False))
        stable_error = site.get("stableError")
        if stable_error is not None and stable_error not in _STABLE_ERRORS:
            raise ValueError(f"callSites[{index}].stableError is not in the stable taxonomy")
        if not parameterized or not transaction_known:
            unresolved.append(call_id)
        plans.append(
            {
                "callId": call_id,
                "language": site_language,
                "targetDriver": target_driver,
                "operations": [
                    "REPLACE_DRIVER_BINDING",
                    "REWRITE_PARAMETER_BINDING",
                    "MAP_STABLE_ERROR",
                    "PRESERVE_TRANSACTION_BOUNDARY",
                    "ADD_TARGET_INTEGRATION_TEST",
                ],
                "safeToApply": parameterized and transaction_known and stable_error is not None,
                "sourceDigest": _required_digest(
                    site.get("sourceDigest"), f"callSites[{index}].sourceDigest"
                ),
            }
        )
    blockers = (
        ()
        if not unresolved
        else (
            _blocker(
                "APPLICATION_CALL_SITE_UNRESOLVED",
                "Some call sites lack typed parameter or transaction contracts.",
            ),
        )
    )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "language": language or "multi-language",
            "patchPlans": plans,
            "unresolvedCallIds": sorted(unresolved),
            "patchPlanDigest": _digest_value(plans),
            "repositoryMutated": False,
        },
        blockers=blockers,
    )


def _handle_behavior(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    cases = _objects(payload.get("cases"), "cases")
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        case_id = _required_string(case.get("caseId"), f"cases[{index}].caseId", pattern=_SAFE_ID)
        mode = str(case.get("mode", "EXACT")).upper()
        source = case.get("source")
        target = case.get("target")
        if mode == "UNORDERED_ROWS":
            if not isinstance(source, list) or not isinstance(target, list):
                raise ValueError(f"cases[{index}] unordered comparison requires arrays")
            passed = Counter(_canonical_json(item) for item in source) == Counter(
                _canonical_json(item) for item in target
            )
        elif mode == "DECIMAL":
            try:
                source_decimal = Decimal(str(source))
                target_decimal = Decimal(str(target))
            except InvalidOperation as error:
                raise ValueError(f"cases[{index}] contains an invalid decimal") from error
            scale = case.get("scale")
            if not isinstance(scale, int) or scale < 0 or scale > 38:
                raise ValueError(f"cases[{index}].scale is invalid")
            quantum = Decimal(1).scaleb(-scale)
            passed = source_decimal.quantize(quantum) == target_decimal.quantize(quantum)
        elif mode == "STABLE_ERROR":
            if source not in _STABLE_ERRORS or target not in _STABLE_ERRORS:
                raise ValueError(f"cases[{index}] error is outside the stable taxonomy")
            passed = source == target
        elif mode in {"EXACT", "ORDERED_ROWS", "SIDE_EFFECTS"}:
            passed = _canonical_json(source) == _canonical_json(target)
        else:
            raise ValueError(f"cases[{index}].mode is unsupported")
        results.append({"caseId": case_id, "mode": mode, "passed": passed})
    failed = [item["caseId"] for item in results if not item["passed"]]
    blockers = (
        ()
        if not failed
        else (_blocker("BEHAVIOR_MISMATCH", f"{len(failed)} differential cases failed."),)
    )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "results": results,
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "failedCaseIds": failed,
            "comparisonDigest": _digest_value(results),
        },
        blockers=blockers,
    )


def _performance_result(payload: Mapping[str, Any]) -> HandlerOutcome:
    cases = _objects(payload.get("cases"), "cases")
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        case_id = _required_string(case.get("caseId"), f"cases[{index}].caseId", pattern=_SAFE_ID)
        _required_digest(
            case.get("sourceEnvironmentDigest"), f"cases[{index}].sourceEnvironmentDigest"
        )
        _required_digest(
            case.get("targetEnvironmentDigest"), f"cases[{index}].targetEnvironmentDigest"
        )
        numeric_fields = (
            "sourceP95Ms",
            "targetP95Ms",
            "sourceThroughput",
            "targetThroughput",
            "maxP95RegressionPct",
            "minThroughputRatio",
        )
        values: dict[str, float] = {}
        for field in numeric_fields:
            raw = case.get(field)
            if not isinstance(raw, int | float) or isinstance(raw, bool) or raw < 0:
                raise ValueError(f"cases[{index}].{field} is invalid")
            values[field] = float(raw)
        if values["sourceP95Ms"] == 0 or values["sourceThroughput"] == 0:
            raise ValueError(f"cases[{index}] source performance baseline must be positive")
        p95_regression = (values["targetP95Ms"] / values["sourceP95Ms"] - 1) * 100
        throughput_ratio = values["targetThroughput"] / values["sourceThroughput"]
        passed = (
            p95_regression <= values["maxP95RegressionPct"]
            and throughput_ratio >= values["minThroughputRatio"]
        )
        results.append(
            {
                "caseId": case_id,
                "p95RegressionPct": round(p95_regression, 6),
                "throughputRatio": round(throughput_ratio, 6),
                "passed": passed,
            }
        )
    failed = [item["caseId"] for item in results if not item["passed"]]
    blockers = (
        ()
        if not failed
        else (
            _blocker("PERFORMANCE_POLICY_FAILED", f"{len(failed)} benchmark cases missed policy."),
        )
    )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "results": results,
            "failedCaseIds": failed,
            "benchmarkDigest": _digest_value(results),
        },
        blockers=blockers,
    )


def _handle_repair(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    findings = _objects(payload.get("findings"), "findings")
    plans: list[dict[str, Any]] = []
    high_risk = 0
    for index, finding in enumerate(findings):
        finding_id = _required_string(
            finding.get("findingId"), f"findings[{index}].findingId", pattern=_SAFE_ID
        )
        domain = _required_string(
            finding.get("domain"), f"findings[{index}].domain", pattern=_SAFE_ID
        ).upper()
        severity = str(finding.get("severity", "HIGH")).upper()
        if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError(f"findings[{index}].severity is invalid")
        risk = (
            "HIGH"
            if domain in {"SECURITY", "DATA", "PRECISION", "TRANSACTION", "CUTOVER"}
            else severity
        )
        approval = risk in {"HIGH", "CRITICAL"}
        high_risk += approval
        plans.append(
            {
                "findingId": finding_id,
                "classification": domain,
                "risk": risk,
                "approvalRequired": approval,
                "operations": [
                    "GENERATE_PATCH_CANDIDATE",
                    "RUN_AFFECTED_E3_E4",
                    "REJECT_ON_REGRESSION",
                ],
                "applied": False,
            }
        )
    blockers = (
        ()
        if high_risk == 0
        else (
            _blocker(
                "REPAIR_APPROVAL_REQUIRED", f"{high_risk} repair plans require human approval."
            ),
        )
    )
    return HandlerOutcome(
        state="READY_FOR_HUMAN_DECISION" if blockers else "LOCAL_COMPLETED",
        artifacts={
            "repairPlans": plans,
            "patchesApplied": 0,
            "repairPlanDigest": _digest_value(plans),
        },
        blockers=blockers,
    )


def _handle_cutover(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    phases = _objects(payload.get("phases"), "phases")
    normalized: list[dict[str, str]] = []
    for index, phase in enumerate(phases):
        phase_id = _required_string(
            phase.get("phaseId"), f"phases[{index}].phaseId", pattern=_SAFE_ID
        )
        state = str(phase.get("state", "NOT_RUN")).upper()
        if state not in {"PASSED", "FAILED", "NOT_RUN"}:
            raise ValueError(f"phases[{index}].state is invalid")
        normalized.append({"phaseId": phase_id, "state": state})
    cdc_gap = payload.get("cdcGap")
    if not isinstance(cdc_gap, int) or cdc_gap < 0:
        raise ValueError("cdcGap must be a non-negative integer")
    reconciliation = bool(payload.get("reconciliationPassed", False))
    rollback = bool(payload.get("rollbackRehearsed", False))
    all_phases = bool(normalized) and all(item["state"] == "PASSED" for item in normalized)
    ready = all_phases and cdc_gap == 0 and reconciliation and rollback
    blockers = (
        ()
        if ready
        else (
            _blocker(
                "CUTOVER_GATE_INCOMPLETE",
                (
                    "Cutover requires passed phases, zero CDC gap, reconciliation, "
                    "and rollback rehearsal."
                ),
            ),
        )
    )
    return HandlerOutcome(
        state="READY_FOR_HUMAN_DECISION" if ready else "LOCAL_FAILED",
        artifacts={
            "phases": normalized,
            "cdcGap": cdc_gap,
            "reconciliationPassed": reconciliation,
            "rollbackRehearsed": rollback,
            "productionSwitchExecuted": False,
            "cutoverPlanDigest": _digest_value({"phases": normalized, "cdcGap": cdc_gap}),
        },
        blockers=blockers,
    )


def _handle_certification(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    gates = _object(payload.get("gates"), "gates")
    required = ("E1", "E2", "E3", "E4", "E5")
    normalized: dict[str, dict[str, Any]] = {}
    failed: list[str] = []
    for gate_id in required:
        gate = _object(gates.get(gate_id), f"gates.{gate_id}")
        state = str(gate.get("state", "NOT_RUN")).upper()
        if state not in {"PASSED", "FAILED", "NOT_RUN"}:
            raise ValueError(f"gates.{gate_id}.state is invalid")
        digest = _required_digest(gate.get("evidenceDigest"), f"gates.{gate_id}.evidenceDigest")
        independent = bool(gate.get("independent", False))
        normalized[gate_id] = {"state": state, "evidenceDigest": digest, "independent": independent}
        if state != "PASSED" or not independent:
            failed.append(gate_id)
    if set(gates) != set(required):
        raise ValueError("certification gates must contain exactly E1 through E5")
    blockers = (
        ()
        if not failed
        else (
            _blocker(
                "CERTIFICATION_EVIDENCE_INCOMPLETE",
                f"Gates without independent pass: {', '.join(failed)}",
            ),
        )
    )
    return HandlerOutcome(
        state="READY_FOR_EXTERNAL_GATE" if not failed else "LOCAL_FAILED",
        artifacts={
            "gates": normalized,
            "failedGates": failed,
            "externalCertificateIssued": False,
            "certificationDecision": "NOT_CERTIFIED",
            "gateDigest": _digest_value(normalized),
        },
        blockers=blockers,
    )


def _handle_security(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    source_grants = set(_strings(payload.get("sourceGrants", []), "sourceGrants"))
    target_grants = set(_strings(payload.get("targetGrants", []), "targetGrants"))
    source_policies = set(_strings(payload.get("sourcePolicies", []), "sourcePolicies"))
    target_policies = set(_strings(payload.get("targetPolicies", []), "targetPolicies"))
    extra_grants = sorted(target_grants - source_grants)
    missing_grants = sorted(source_grants - target_grants)
    missing_policies = sorted(source_policies - target_policies)
    blockers: list[Mapping[str, Any]] = []
    if extra_grants:
        blockers.append(
            _blocker("PRIVILEGE_BROADENING", "Target introduces grants absent from the source.")
        )
    if missing_policies:
        blockers.append(
            _blocker("ROW_POLICY_MISSING", "Target does not preserve all source row policies.")
        )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "extraTargetGrants": extra_grants,
            "missingTargetGrants": missing_grants,
            "missingTargetPolicies": missing_policies,
            "securityDiffDigest": _digest_value(
                {"extra": extra_grants, "missing": missing_grants, "policies": missing_policies}
            ),
        },
        blockers=tuple(blockers),
    )


def _handle_evidence(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    entries = _objects(payload.get("entries"), "entries")
    by_id: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        evidence_id = _required_string(
            entry.get("evidenceId"), f"entries[{index}].evidenceId", pattern=_SAFE_ID
        )
        if evidence_id in by_id:
            raise ValueError(f"duplicate evidenceId: {evidence_id}")
        by_id[evidence_id] = {
            "evidenceId": evidence_id,
            "contentDigest": _required_digest(
                entry.get("contentDigest"), f"entries[{index}].contentDigest"
            ),
            "refs": sorted(_strings(entry.get("refs", []), f"entries[{index}].refs")),
            "producer": _required_string(
                entry.get("producer"), f"entries[{index}].producer", pattern=_SAFE_ID
            ),
            "verifier": _required_string(
                entry.get("verifier"), f"entries[{index}].verifier", pattern=_SAFE_ID
            ),
        }
        if by_id[evidence_id]["producer"] == by_id[evidence_id]["verifier"]:
            raise ValueError(f"evidence {evidence_id} is self-verified")
    missing = sorted({ref for entry in by_id.values() for ref in entry["refs"] if ref not in by_id})
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(evidence_id: str) -> None:
        if evidence_id in visiting:
            raise ValueError("evidence dependency graph contains a cycle")
        if evidence_id in visited:
            return
        visiting.add(evidence_id)
        for ref in by_id[evidence_id]["refs"]:
            if ref in by_id:
                visit(ref)
        visiting.remove(evidence_id)
        visited.add(evidence_id)

    for evidence_id in sorted(by_id):
        visit(evidence_id)
    blockers = (
        ()
        if not missing
        else (
            _blocker(
                "EVIDENCE_REFERENCE_MISSING", "Evidence graph contains unresolved references."
            ),
        )
    )
    ordered = [by_id[evidence_id] for evidence_id in sorted(by_id)]
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "entries": ordered,
            "entryCount": len(ordered),
            "missingReferences": missing,
            "ledgerDigest": _digest_value(ordered),
        },
        blockers=blockers,
    )


def _handle_release(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    checks = _objects(payload.get("checks"), "checks")
    normalized: list[dict[str, str]] = []
    failed: list[str] = []
    for index, check in enumerate(checks):
        check_id = _required_string(
            check.get("checkId"), f"checks[{index}].checkId", pattern=_SAFE_ID
        )
        state = str(check.get("state", "NOT_RUN")).upper()
        if state not in {"PASSED", "FAILED", "NOT_RUN"}:
            raise ValueError(f"checks[{index}].state is invalid")
        normalized.append({"checkId": check_id, "state": state})
        if state != "PASSED":
            failed.append(check_id)
    blockers = (
        ()
        if not failed
        else (
            _blocker(
                "RELEASE_CHECKS_INCOMPLETE", f"Release checks not passed: {', '.join(failed)}"
            ),
        )
    )
    return HandlerOutcome(
        state="READY_FOR_EXTERNAL_GATE" if not failed and normalized else "LOCAL_FAILED",
        artifacts={
            "checks": normalized,
            "failedChecks": failed,
            "released": False,
            "releaseDecision": "READY_FOR_EXTERNAL_GATE"
            if not failed and normalized
            else "BLOCKED",
        },
        blockers=blockers,
    )


def _catalog_objects(payload: Mapping[str, Any], source_id: str) -> HandlerOutcome:
    objects = _objects(payload.get("catalogObjects"), "catalogObjects")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(objects):
        normalized.append(
            {
                "objectId": _required_string(
                    item.get("objectId"), f"catalogObjects[{index}].objectId", pattern=_SAFE_ID
                ),
                "kind": _required_string(
                    item.get("kind"), f"catalogObjects[{index}].kind", pattern=_SAFE_ID
                ).upper(),
                "definitionDigest": _required_digest(
                    item.get("definitionDigest"), f"catalogObjects[{index}].definitionDigest"
                ),
                "unsupported": bool(item.get("unsupported", False)),
            }
        )
    return HandlerOutcome(
        state="LOCAL_COMPLETED",
        artifacts={
            "sourceAdapter": source_id,
            "mode": "TYPED_CATALOG",
            "objects": normalized,
            "unsupportedCount": sum(bool(item["unsupported"]) for item in normalized),
            "catalogDigest": _digest_value(normalized),
        },
    )


def _handle_source(payload: Mapping[str, Any], spec: SkillSpec) -> HandlerOutcome:
    source_id = str(spec.bound_value)
    if "catalogObjects" in payload:
        return _catalog_objects(payload, source_id)
    sql = _required_string(payload.get("sql"), "sql", maximum=MAX_REQUEST_BYTES)
    if source_id in {"db2-luw", "sybase-ase"}:
        return HandlerOutcome(
            state="LOCAL_FAILED",
            artifacts={"sourceAdapter": source_id, "mode": "RAW_SQL", "statements": []},
            blockers=(
                _blocker(
                    "NATIVE_SOURCE_PARSER_REQUIRED",
                    (
                        f"{source_id} raw SQL needs an exact native parser; use typed "
                        "catalogObjects until configured."
                    ),
                ),
            ),
        )
    _require_pinned_parser()
    profile = profile_by_id(source_id)
    try:
        parsed = sqlglot.parse(sql, read=profile.dialect, error_level=ErrorLevel.RAISE)
    except (ParseError, TokenError) as error:
        return HandlerOutcome(
            state="LOCAL_FAILED",
            artifacts={"sourceAdapter": source_id, "mode": "TYPED_AST", "statements": []},
            blockers=(_blocker("SOURCE_PARSE_FAILED", type(error).__name__),),
        )
    statements: list[dict[str, Any]] = []
    opaque = 0
    for index, statement in enumerate(parsed):
        if not isinstance(statement, exp.Expression):
            opaque += 1
            continue
        opaque += isinstance(statement, exp.Command)
        statements.append(
            {
                "index": index,
                "kind": statement.key.upper(),
                "astDigest": _digest_value(statement.dump()),
                "opaque": isinstance(statement, exp.Command),
            }
        )
    blockers = (
        ()
        if opaque == 0
        else (
            _blocker(
                "OPAQUE_SOURCE_COMMAND",
                f"{opaque} source statements were parsed as opaque commands.",
            ),
        )
    )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "sourceAdapter": source_id,
            "mode": "TYPED_AST",
            "profile": profile.to_dict(),
            "statements": statements,
            "opaqueCount": opaque,
            "sourceDigest": _digest_text(sql),
        },
        blockers=blockers,
    )


def _handle_target(payload: Mapping[str, Any], spec: SkillSpec) -> HandlerOutcome:
    target_id = str(spec.bound_value)
    target = _object(payload.get("target"), "target")
    if target.get("id") != target_id:
        raise ValueError(f"target.id must be the handler-bound target {target_id}")
    version = _required_string(target.get("version"), "target.version", pattern=_SAFE_ID)
    edition = _required_string(target.get("edition"), "target.edition", pattern=_SAFE_ID)
    mode = _required_string(
        target.get("compatibilityMode"), "target.compatibilityMode", pattern=_SAFE_ID
    )
    driver = _required_string(target.get("driver"), "target.driver", pattern=_SAFE_ID)
    snapshot = _required_digest(
        target.get("capabilitySnapshotDigest"), "target.capabilitySnapshotDigest"
    )
    capabilities = commercial_capabilities()
    current_snapshot = str(capabilities["capabilitySnapshotDigest"])
    if snapshot != current_snapshot:
        raise ValueError("target.capabilitySnapshotDigest does not match the current registry")
    catalog_target = next(item for item in capabilities["targets"] if item["id"] == target_id)
    return HandlerOutcome(
        state="BLOCKED_EXTERNAL",
        artifacts={
            "targetId": target_id,
            "targetLabel": catalog_target["label"],
            "adapterId": catalog_target["adapterId"],
            "exactTuple": {
                "version": version,
                "edition": edition,
                "compatibilityMode": mode,
                "driver": driver,
            },
            "capabilitySnapshotDigest": snapshot,
            "adapterProtocol": {
                "discover": "IMPLEMENTED_CONTRACT",
                "render": "EVIDENCE_GATED",
                "apply": "AUTHORIZATION_GATED",
                "introspect": "EVIDENCE_GATED",
                "mapError": "EVIDENCE_GATED",
                "capturePlan": "EVIDENCE_GATED",
                "movementHooks": "EVIDENCE_GATED",
                "operationalChecks": "EVIDENCE_GATED",
            },
            "targetSql": None,
        },
        blockers=(
            _blocker(
                "TARGET_RUNTIME_AND_CAPABILITY_EVIDENCE_REQUIRED",
                (
                    "Adapter code is bound, but no independently verified target runtime "
                    "or renderer evidence was supplied."
                ),
            ),
        ),
    )


def _handle_route_matrix(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    evidence_rows = _objects(payload.get("routeEvidence", []), "routeEvidence")
    evidence = {str(item.get("routeId")): item for item in evidence_rows}
    capabilities = commercial_capabilities()
    routes: list[dict[str, Any]] = []
    for route in capabilities["plannedRoutes"]:
        route_id = str(route["id"])
        row = evidence.get(route_id)
        state = "SPEC_ONLY" if row is None else str(row.get("state", "NOT_RUN")).upper()
        if state not in {"SPEC_ONLY", "NOT_RUN", "LOCAL_PASSED", "EXTERNAL_PASSED", "FAILED"}:
            raise ValueError(f"routeEvidence state is invalid for {route_id}")
        routes.append({**route, "runtimeState": state})
    unknown = sorted(set(evidence) - {str(route["id"]) for route in routes})
    if unknown:
        raise ValueError(f"routeEvidence contains unknown routes: {unknown}")
    return HandlerOutcome(
        state="LOCAL_COMPLETED",
        artifacts={
            "routes": routes,
            "routeCount": len(routes),
            "externalPassed": sum(item["runtimeState"] == "EXTERNAL_PASSED" for item in routes),
            "routeMatrixDigest": _digest_value(routes),
        },
    )


def _handle_mutation(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    mutants = _objects(payload.get("mutants"), "mutants")
    results: list[dict[str, Any]] = []
    critical_missed: list[str] = []
    for index, mutant in enumerate(mutants):
        mutant_id = _required_string(
            mutant.get("mutantId"), f"mutants[{index}].mutantId", pattern=_SAFE_ID
        )
        critical = bool(mutant.get("critical", False))
        detected = bool(mutant.get("detected", False))
        if critical and not detected:
            critical_missed.append(mutant_id)
        results.append({"mutantId": mutant_id, "critical": critical, "detected": detected})
    detected_count = sum(item["detected"] for item in results)
    score = detected_count / len(results) if results else 0.0
    blockers = (
        ()
        if not critical_missed
        else (
            _blocker(
                "CRITICAL_MUTATION_SURVIVED",
                "At least one critical incorrect conversion was not detected.",
            ),
        )
    )
    return HandlerOutcome(
        state="LOCAL_COMPLETED" if not blockers else "LOCAL_FAILED",
        artifacts={
            "mutants": results,
            "mutationScore": round(score, 6),
            "criticalMissed": critical_missed,
            "mutationDigest": _digest_value(results),
        },
        blockers=blockers,
    )


def _handle_estimate(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    counts = _object(payload.get("objectCounts"), "objectCounts")
    weights = _object(payload.get("weights"), "weights")
    total = Decimal(0)
    normalized: dict[str, dict[str, str | int]] = {}
    for kind, raw_count in counts.items():
        if not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError(f"objectCounts.{kind} must be a non-negative integer")
        try:
            weight = Decimal(str(weights.get(kind, "1")))
        except InvalidOperation as error:
            raise ValueError(f"weights.{kind} is invalid") from error
        if weight <= 0 or weight > 1_000:
            raise ValueError(f"weights.{kind} must be positive and bounded")
        subtotal = weight * raw_count
        total += subtotal
        normalized[kind] = {"count": raw_count, "weight": str(weight), "points": str(subtotal)}
    low = total * Decimal("0.8")
    high = total * Decimal("1.35")
    return HandlerOutcome(
        state="LOCAL_COMPLETED",
        artifacts={
            "breakdown": dict(sorted(normalized.items())),
            "estimatePoints": str(total),
            "range": {"low": str(low), "high": str(high)},
            "notACommercialQuote": True,
            "estimateDigest": _digest_value(normalized),
        },
    )


def _handle_vendor_bridge(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    provider = _required_string(payload.get("provider"), "provider", pattern=_SAFE_ID)
    operation = _required_string(payload.get("operation"), "operation", pattern=_SAFE_ID).upper()
    if operation not in {
        "DISCOVER",
        "RENDER",
        "APPLY_SANDBOX",
        "INTROSPECT",
        "CAPTURE_PLAN",
        "MOVEMENT_HOOKS",
    }:
        raise ValueError("vendor bridge operation is not allowlisted")
    credential_ref = _required_string(
        payload.get("credentialRef"), "credentialRef", pattern=_SAFE_ID
    )
    authorized = bool(payload.get("authorized", False))
    return HandlerOutcome(
        state="BLOCKED_EXTERNAL",
        artifacts={
            "provider": provider,
            "operation": operation,
            "credentialRef": credential_ref,
            "authorizationPresent": authorized,
            "providerCalled": False,
            "invocationDigest": _digest_value(
                {"provider": provider, "operation": operation, "credentialRef": credential_ref}
            ),
        },
        blockers=(
            _blocker(
                "VENDOR_RUNTIME_NOT_BOUND",
                (
                    "The bridge contract is valid, but this local runtime has no "
                    "authorized vendor process binding."
                ),
            ),
        ),
    )


def _handle_observability(payload: Mapping[str, Any], _: SkillSpec) -> HandlerOutcome:
    events = _objects(payload.get("events"), "events")
    counters: Counter[str] = Counter()
    alerts: list[dict[str, str]] = []
    normalized: list[dict[str, str]] = []
    for index, event in enumerate(events):
        event_id = _required_string(
            event.get("eventId"), f"events[{index}].eventId", pattern=_SAFE_ID
        )
        state = _required_string(
            event.get("state"), f"events[{index}].state", pattern=_SAFE_ID
        ).upper()
        severity = str(event.get("severity", "INFO")).upper()
        if severity not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"events[{index}].severity is invalid")
        counters[state] += 1
        normalized.append({"eventId": event_id, "state": state, "severity": severity})
        if state in {"FAILED", "BLOCKED", "STALE", "UNKNOWN"} and severity in {"ERROR", "CRITICAL"}:
            alerts.append({"eventId": event_id, "reason": f"{state}_{severity}"})
    return HandlerOutcome(
        state="LOCAL_COMPLETED",
        artifacts={
            "counters": dict(sorted(counters.items())),
            "alerts": alerts,
            "eventDigest": _digest_value(normalized),
            "externalMetricsPublished": False,
        },
    )


def _handler_for(spec: SkillSpec) -> Callable[[Mapping[str, Any], SkillSpec], HandlerOutcome]:
    if spec.handler_id == "orchestrate":
        return _handle_orchestrator
    if spec.handler_id == "inventory":
        return _handle_inventory
    if spec.handler_id == "semantic-ir":
        return _handle_semantic_ir
    if spec.handler_id == "rule-dsl":
        return _handle_rule_dsl
    if spec.handler_id == "cdc-plan":
        return _handle_cdc
    if spec.handler_id in {"ddl-conversion", "sql-conversion"}:
        return _handle_conversion
    if spec.handler_id == "procedural-strategy":
        return _handle_procedural
    if spec.handler_id == "application-plan":
        return lambda payload, _spec: _app_patch_plan(payload, None)
    if spec.handler_id == "behavior-verify":
        return _handle_behavior
    if spec.handler_id in {"performance-verify", "benchmark-gate"}:
        return lambda payload, _spec: _performance_result(payload)
    if spec.handler_id == "repair-plan":
        return _handle_repair
    if spec.handler_id == "cutover-gate":
        return _handle_cutover
    if spec.handler_id == "certification-gate":
        return _handle_certification
    if spec.handler_id == "security-diff":
        return _handle_security
    if spec.handler_id == "evidence-ledger":
        return _handle_evidence
    if spec.handler_id == "release-gate":
        return _handle_release
    if spec.handler_id.startswith("source:"):
        return _handle_source
    if spec.handler_id.startswith("application:"):
        return lambda payload, bound_spec: _app_patch_plan(payload, bound_spec.bound_value)
    if spec.handler_id.startswith("target:"):
        return _handle_target
    if spec.handler_id == "route-matrix":
        return _handle_route_matrix
    if spec.handler_id == "mutation-gate":
        return _handle_mutation
    if spec.handler_id == "estimate":
        return _handle_estimate
    if spec.handler_id == "vendor-bridge":
        return _handle_vendor_bridge
    if spec.handler_id == "observability":
        return _handle_observability
    raise RuntimeError(f"no local handler bound for {spec.skill_id}")


HANDLERS = {spec.skill_id: _handler_for(spec) for spec in SKILL_SPECS}
if set(HANDLERS) != set(SKILLS_BY_ID):
    raise RuntimeError("ChinaDB handler registry is incomplete")


def skill_capabilities() -> dict[str, Any]:
    """Return the exact code binding matrix without raising external status."""

    bindings = [
        {
            "skillId": spec.skill_id,
            "alias": spec.alias,
            "handlerId": spec.handler_id,
            "category": spec.category,
            "dependencies": list(spec.dependencies),
            "externalEffects": list(spec.external_effects),
            "localCodeStatus": "CODE_IMPLEMENTED",
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for spec in SKILL_SPECS
    ]
    return {
        "schemaVersion": "1.0",
        "package": PACKAGE,
        "runtimeVersion": RUNTIME_VERSION,
        "skillCount": len(bindings),
        "codeImplementedCount": len(bindings),
        "boundedLocalHandlerCoverage": {
            "implemented": len(bindings),
            "total": len(bindings),
            "rate": 1.0,
        },
        "importedSpecificationStatus": "SPEC_ONLY",
        "productionDefinitionOfDoneCount": 0,
        "productionDefinitionOfDone": "BLOCKED_EXTERNAL_EVIDENCE",
        "bindings": bindings,
        "bindingDigest": _digest_value(bindings),
        "externalExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "claim": (
            "All 47 exact Skills have repository-owned bounded local handlers. "
            "Provider/database/repository mutations remain authorization- and evidence-gated."
        ),
    }


def execute_skill(skill_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one exact bounded handler and return content-addressed evidence."""

    if skill_id not in SKILLS_BY_ID:
        raise ValueError(f"unknown ChinaDB Skill id: {skill_id}")
    raw_payload = _object(payload, "payload")
    encoded = _canonical_json(raw_payload).encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("Skill payload exceeds the 1 MiB canonical JSON limit")
    _walk_request(raw_payload)
    scope = _validate_scope(raw_payload)
    spec = SKILLS_BY_ID[skill_id]
    outcome = HANDLERS[skill_id](raw_payload, spec)
    artifacts = dict(outcome.artifacts)
    artifact_digest = _digest_value(artifacts)
    result: dict[str, Any] = {
        "schemaVersion": "1.0",
        "package": PACKAGE,
        "runtimeVersion": RUNTIME_VERSION,
        "skillId": skill_id,
        "alias": spec.alias,
        "handlerId": spec.handler_id,
        "scope": scope,
        "state": outcome.state,
        "localCodeStatus": "CODE_IMPLEMENTED",
        "requestDigest": _digest_text(encoded.decode("utf-8")),
        "artifactDigest": artifact_digest,
        "artifacts": artifacts,
        "checks": [dict(item) for item in outcome.checks],
        "blockers": [dict(item) for item in outcome.blockers],
        "effects": {
            "declaredExternalEffects": list(spec.external_effects),
            "externalEffectsExecuted": [],
        },
        "verification": {
            "localHandler": "PASSED" if outcome.state != "LOCAL_FAILED" else "FAILED",
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
        },
        "certification": "NOT_CERTIFIED",
    }
    result["resultDigest"] = _digest_value(result)
    return result
