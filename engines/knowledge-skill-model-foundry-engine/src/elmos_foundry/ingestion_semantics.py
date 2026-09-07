"""Exact, bounded local semantics for six Knowledge Fabric ingestion Skills.

The handlers consume caller-supplied structured facts.  They never connect to
repositories, databases, telemetry backends, or legal/license services.  Every
result keeps source authorization, independent verification, and external
evidence explicit instead of inferring them from caller data.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import PurePosixPath
import re
import unicodedata
from typing import Any

from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    _exact_mapping,
    _mapping,
    _response,
    _sequence,
    _text,
)
from .store import FoundryStore


INGESTION_SEMANTIC_SKILLS: frozenset[str] = frozenset(
    {
        "api-contract-ingestion",
        "database-metadata-ingestion",
        "license-and-rights-classification",
        "repository-incremental-ingestion",
        "runtime-trace-ingestion",
        "source-freshness-and-expiry",
    }
)

_INPUT_KEYS = {
    "repository",
    "document",
    "API schema",
    "database metadata",
    "runtime trace",
    "ticket or incident",
}
_MAX_ITEMS = 4_096
_PATH_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _integer(value: Any, label: str, *, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return int(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    text = _text(value, label, maximum=64)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None or "T" not in text:
        raise ValueError(f"{label} must include time and timezone")
    return result.astimezone(timezone.utc)


def _strings(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_ITEMS,
) -> list[str]:
    result = [
        _text(item, label, maximum=1_024)
        for item in _sequence(value, label, minimum=minimum, maximum=maximum)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _values(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    values = _exact_mapping(payload.get("inputs"), "inputs", _INPUT_KEYS)
    canonical_value(values)
    for key in _INPUT_KEYS:
        if not _mapping(values[key], key):
            raise ValueError(f"{key} must be a non-empty object")
    return values


def _scope(source: Mapping[str, Any], scope: TenantScope) -> None:
    if source.get("tenant_id") != scope.tenant_id or source.get("project_id") != scope.project_id:
        raise ValueError("ingestion source crosses the authenticated tenant/project boundary")


def _path(value: Any, label: str) -> str:
    text = unicodedata.normalize("NFC", _text(value, label, maximum=1_024))
    path = PurePosixPath(text)
    if (
        text != path.as_posix()
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or _PATH_CONTROL.search(text)
    ):
        raise ValueError(f"{label} must be a canonical relative POSIX path")
    return text


def _base_result(
    skill: str,
    values: Mapping[str, Any],
    scope: TenantScope,
    normalized: Mapping[str, Any],
    *,
    rights: Mapping[str, Any] | None = None,
    freshness: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    source_digests = {
        key: canonical_digest(values[key]) for key in sorted(_INPUT_KEYS)
    }
    artifact = {
        "schema_version": "elmos.foundry.local-ingestion.v1",
        "skill_name": skill,
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "workspace_digest": scope.workspace_digest,
        "revision_set_id": scope.revision_set_id,
        "normalized": canonical_value(normalized),
        "source_digests": source_digests,
    }
    artifact_digest = canonical_digest(artifact)
    return _response(
        {
            "normalized artifact": {
                **artifact,
                "artifact_id": "ingestion-" + artifact_digest[7:39],
                "content_digest": artifact_digest,
                "external_effects_executed": False,
            },
            "source provenance": {
                "source_digests": source_digests,
                "scope_digest": scope.binding_digest,
                "catalog_source_bound": True,
                "caller_facts_verified": False,
                "source_authorization_status": "NOT_RUN",
                "independent_verification_status": "NOT_RUN",
            },
            "rights classification": canonical_value(
                rights
                or {
                    "decision": "UNVERIFIED",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "legal_review_status": "NOT_RUN",
                }
            ),
            "freshness status": canonical_value(
                freshness
                or {
                    "status": "UNVERIFIED",
                    "refresh_required": True,
                    "external_validation_status": "NOT_RUN",
                }
            ),
        }
    )


def _file_index(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    folded: dict[str, str] = {}
    for index, raw in enumerate(_sequence(value, label, maximum=_MAX_ITEMS)):
        row = _exact_mapping(raw, f"{label}[{index}]", {"path", "content_digest", "mode"})
        path = _path(row["path"], f"{label}[{index}].path")
        if path in result:
            raise ValueError(f"{label} contains a duplicate path")
        collision = path.casefold()
        if collision in folded and folded[collision] != path:
            raise ValueError(f"{label} contains a case-fold path collision")
        folded[collision] = path
        validate_digest(row["content_digest"], "content_digest")
        if row["mode"] not in {"REGULAR", "EXECUTABLE", "SYMLINK"}:
            raise ValueError("file mode is unsupported")
        result[path] = {
            "path": path,
            "content_digest": row["content_digest"],
            "mode": row["mode"],
        }
    return result


def _repository_incremental(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _values(payload)
    repository = _exact_mapping(
        values["repository"],
        "repository",
        {
            "repository_id",
            "tenant_id",
            "project_id",
            "base_revision",
            "target_revision",
            "base_files",
            "target_files",
        },
    )
    _scope(repository, scope)
    require_identifier(repository["repository_id"], "repository_id")
    for key in ("base_revision", "target_revision"):
        validate_digest(repository[key], key)
    if repository["base_revision"] == repository["target_revision"]:
        raise ValueError("incremental ingestion revisions must differ")
    base = _file_index(repository["base_files"], "base_files")
    target = _file_index(repository["target_files"], "target_files")
    added = sorted(set(target) - set(base))
    deleted = sorted(set(base) - set(target))
    modified = sorted(
        path for path in set(base) & set(target) if base[path] != target[path]
    )
    unchanged = sorted(set(base) & set(target) - set(modified))
    delta = {
        "repository_id": repository["repository_id"],
        "base_revision": repository["base_revision"],
        "target_revision": repository["target_revision"],
        "added": [{"path": path, "after": target[path]} for path in added],
        "modified": [
            {"path": path, "before": base[path], "after": target[path]} for path in modified
        ],
        "deleted": [{"path": path, "before": base[path]} for path in deleted],
        "unchanged_paths": unchanged,
        "target_tree_digest": canonical_digest([target[path] for path in sorted(target)]),
        "native_repository_read_status": "NOT_RUN",
    }
    return _base_result(skill, values, scope, delta)


def _api_contract(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _values(payload)
    schema = _exact_mapping(
        values["API schema"],
        "API schema",
        {"format", "version", "source_digest", "operations"},
    )
    if schema["format"] not in {"OPENAPI", "ASYNCAPI", "GRAPHQL", "PROTOBUF", "IDL"}:
        raise ValueError("API schema format is unsupported")
    _text(schema["version"], "API schema.version", maximum=64)
    validate_digest(schema["source_digest"], "API schema.source_digest")
    operations: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(_sequence(schema["operations"], "operations", maximum=_MAX_ITEMS)):
        row = _exact_mapping(
            raw,
            f"operations[{index}]",
            {"id", "kind", "method", "path", "input_digest", "output_digest"},
        )
        identity = require_identifier(row["id"], "operation.id")
        if identity in operations:
            raise ValueError("API schema contains duplicate operation identities")
        if row["kind"] not in {"HTTP", "EVENT", "QUERY", "MUTATION", "RPC"}:
            raise ValueError("API operation kind is unsupported")
        method = _text(row["method"], "operation.method", maximum=64).upper()
        path = _text(row["path"], "operation.path", maximum=1_024)
        for key in ("input_digest", "output_digest"):
            validate_digest(row[key], f"operation.{key}")
        operations[identity] = {
            **row,
            "method": method,
            "path": path,
        }
    normalized = {
        "format": schema["format"],
        "version": schema["version"],
        "source_digest": schema["source_digest"],
        "operations": [operations[name] for name in sorted(operations)],
        "operation_count": len(operations),
        "native_parser_status": "NOT_RUN",
    }
    return _base_result(skill, values, scope, normalized)


def _database_metadata(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _values(payload)
    metadata = _exact_mapping(
        values["database metadata"],
        "database metadata",
        {"engine", "engine_version", "snapshot_digest", "objects", "plans"},
    )
    engine = require_identifier(metadata["engine"], "engine")
    version = _text(metadata["engine_version"], "engine_version", maximum=64)
    validate_digest(metadata["snapshot_digest"], "snapshot_digest")
    objects: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(_sequence(metadata["objects"], "objects", maximum=_MAX_ITEMS)):
        row = _exact_mapping(
            raw,
            f"objects[{index}]",
            {"kind", "schema", "name", "definition_digest", "dependencies"},
        )
        if row["kind"] not in {"TABLE", "VIEW", "ROUTINE", "TRIGGER", "INDEX", "CONSTRAINT"}:
            raise ValueError("database object kind is unsupported")
        schema = require_identifier(row["schema"], "object.schema")
        name = require_identifier(row["name"], "object.name")
        identity = f"{schema}.{name}"
        if identity in objects:
            raise ValueError("database metadata contains duplicate object identities")
        validate_digest(row["definition_digest"], "definition_digest")
        dependencies = _strings(row["dependencies"], "object.dependencies")
        objects[identity] = {**row, "id": identity, "dependencies": sorted(dependencies)}
    for identity, row in objects.items():
        missing = sorted(set(row["dependencies"]) - set(objects))
        if missing:
            raise ValueError(f"database object {identity} has unknown dependencies: {missing}")
    plans: list[Mapping[str, Any]] = []
    plan_ids: set[str] = set()
    for index, raw in enumerate(_sequence(metadata["plans"], "plans", maximum=_MAX_ITEMS)):
        row = _exact_mapping(raw, f"plans[{index}]", {"query_id", "plan_digest", "objects"})
        query_id = require_identifier(row["query_id"], "query_id")
        if query_id in plan_ids:
            raise ValueError("database metadata contains duplicate query plans")
        plan_ids.add(query_id)
        validate_digest(row["plan_digest"], "plan_digest")
        references = sorted(_strings(row["objects"], "plan.objects"))
        if set(references) - set(objects):
            raise ValueError("query plan references unknown database objects")
        plans.append({**row, "objects": references})
    normalized = {
        "engine": engine,
        "engine_version": version,
        "snapshot_digest": metadata["snapshot_digest"],
        "objects": [objects[name] for name in sorted(objects)],
        "plans": sorted(plans, key=lambda item: str(item["query_id"])),
        "native_database_status": "NOT_RUN",
    }
    return _base_result(skill, values, scope, normalized)


def _runtime_trace(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _values(payload)
    trace = _exact_mapping(
        values["runtime trace"],
        "runtime trace",
        {"format", "source_digest", "spans", "metrics", "logs"},
    )
    if trace["format"] not in {"OTLP", "ELMOS_TRACE_V1"}:
        raise ValueError("runtime trace format is unsupported")
    validate_digest(trace["source_digest"], "runtime trace.source_digest")
    spans: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(_sequence(trace["spans"], "spans", maximum=_MAX_ITEMS)):
        row = _exact_mapping(
            raw,
            f"spans[{index}]",
            {"span_id", "parent_span_id", "service", "operation", "start_ns", "end_ns", "code_entity"},
        )
        span_id = require_identifier(row["span_id"], "span_id")
        if span_id in spans:
            raise ValueError("runtime trace contains duplicate span identities")
        parent = row["parent_span_id"]
        if parent is not None:
            require_identifier(parent, "parent_span_id")
        start = _integer(row["start_ns"], "start_ns")
        end = _integer(row["end_ns"], "end_ns")
        if end < start:
            raise ValueError("span end precedes start")
        spans[span_id] = {
            **row,
            "service": require_identifier(row["service"], "service"),
            "operation": _text(row["operation"], "operation"),
            "code_entity": _text(row["code_entity"], "code_entity"),
            "duration_ns": end - start,
        }
    for span_id, row in spans.items():
        parent = row["parent_span_id"]
        if parent is not None and (parent not in spans or parent == span_id):
            raise ValueError("runtime trace contains a dangling or self parent")
    for span_id in spans:
        visited: set[str] = set()
        current: str | None = span_id
        while current is not None:
            if current in visited:
                raise ValueError("runtime trace span graph contains a cycle")
            visited.add(current)
            parent_value = spans[current]["parent_span_id"]
            current = str(parent_value) if parent_value is not None else None
    metrics: list[Mapping[str, Any]] = []
    for index, raw in enumerate(_sequence(trace["metrics"], "metrics", maximum=_MAX_ITEMS)):
        row = _exact_mapping(raw, f"metrics[{index}]", {"name", "value", "unit"})
        value = row["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("metric value must be numeric")
        metrics.append(
            {
                "name": require_identifier(row["name"], "metric.name"),
                "value": value,
                "unit": require_identifier(row["unit"], "metric.unit"),
            }
        )
    logs: list[Mapping[str, Any]] = []
    for index, raw in enumerate(_sequence(trace["logs"], "logs", maximum=_MAX_ITEMS)):
        row = _exact_mapping(raw, f"logs[{index}]", {"timestamp", "severity", "message_digest", "span_id"})
        _timestamp(row["timestamp"], "log.timestamp")
        if row["severity"] not in {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"}:
            raise ValueError("log severity is unsupported")
        validate_digest(row["message_digest"], "message_digest")
        if row["span_id"] not in spans:
            raise ValueError("log references an unknown span")
        logs.append(dict(row))
    normalized = {
        "format": trace["format"],
        "source_digest": trace["source_digest"],
        "spans": [spans[name] for name in sorted(spans)],
        "metrics": sorted(metrics, key=lambda item: (str(item["name"]), str(item["unit"]))),
        "logs": sorted(logs, key=lambda item: (str(item["timestamp"]), str(item["span_id"]))),
        "code_entity_counts": dict(sorted(Counter(str(row["code_entity"]) for row in spans.values()).items())),
        "native_telemetry_read_status": "NOT_RUN",
    }
    return _base_result(skill, values, scope, normalized)


def _freshness(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _values(payload)
    document = _exact_mapping(
        values["document"],
        "document",
        {
            "source_id",
            "version",
            "observed_at",
            "valid_from",
            "expires_at",
            "last_verified_at",
            "refresh_sla_seconds",
            "applies_to_versions",
        },
    )
    ticket = _exact_mapping(
        values["ticket or incident"], "ticket or incident", {"evaluated_at", "target_version"}
    )
    observed = _timestamp(document["observed_at"], "observed_at")
    valid_from = _timestamp(document["valid_from"], "valid_from")
    expires = _timestamp(document["expires_at"], "expires_at")
    verified = _timestamp(document["last_verified_at"], "last_verified_at")
    evaluated = _timestamp(ticket["evaluated_at"], "evaluated_at")
    if not observed <= verified <= evaluated or not valid_from < expires:
        raise ValueError("freshness timestamps are inconsistent")
    sla = _integer(document["refresh_sla_seconds"], "refresh_sla_seconds", minimum=1)
    versions = _strings(document["applies_to_versions"], "applies_to_versions", minimum=1)
    target_version = _text(ticket["target_version"], "target_version", maximum=128)
    elapsed = int((evaluated - verified).total_seconds())
    if target_version not in versions:
        status = "INAPPLICABLE"
    elif evaluated < valid_from:
        status = "NOT_YET_VALID"
    elif evaluated >= expires:
        status = "EXPIRED"
    elif elapsed > sla:
        status = "REFRESH_DUE"
    else:
        status = "FRESH"
    freshness = {
        "source_id": require_identifier(document["source_id"], "source_id"),
        "version": _text(document["version"], "version", maximum=128),
        "target_version": target_version,
        "status": status,
        "age_since_verification_seconds": elapsed,
        "refresh_sla_seconds": sla,
        "refresh_required": status in {"EXPIRED", "REFRESH_DUE"},
        "evaluated_at": ticket["evaluated_at"],
        "external_validation_status": "NOT_RUN",
    }
    return _base_result(skill, values, scope, freshness, freshness=freshness)


def _rights(
    skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
) -> Mapping[str, Any]:
    values = _values(payload)
    document = _exact_mapping(
        values["document"],
        "document",
        {
            "source_id",
            "content_digest",
            "license_expression",
            "contract_restrictions",
            "training_use",
            "redistribution",
            "attribution_required",
            "notice_digest",
            "territories",
            "purposes",
        },
    )
    validate_digest(document["content_digest"], "content_digest")
    restrictions = sorted(_strings(document["contract_restrictions"], "contract_restrictions"))
    territories = sorted(_strings(document["territories"], "territories", minimum=1))
    purposes = sorted(_strings(document["purposes"], "purposes", minimum=1))
    training = document["training_use"]
    redistribution = document["redistribution"]
    if training not in {"ALLOW", "DENY", "REVIEW_REQUIRED"}:
        raise ValueError("training_use is unsupported")
    if redistribution not in {"ALLOW", "DENY", "REVIEW_REQUIRED"}:
        raise ValueError("redistribution is unsupported")
    attribution = _boolean(document["attribution_required"], "attribution_required")
    notice = document["notice_digest"]
    if notice is not None:
        validate_digest(notice, "notice_digest")
    if attribution and notice is None:
        raise ValueError("attribution requires a notice digest")
    license_expression = _text(document["license_expression"], "license_expression", maximum=512)
    if license_expression == "UNKNOWN" or restrictions or "*" not in purposes:
        decision = "REVIEW_REQUIRED"
    elif "*" not in territories:
        decision = "REVIEW_REQUIRED"
    elif training == "DENY" and redistribution == "DENY":
        decision = "DENY"
    elif "REVIEW_REQUIRED" in {training, redistribution}:
        decision = "REVIEW_REQUIRED"
    else:
        decision = "CALLER_DECLARED"
    rights = {
        "source_id": require_identifier(document["source_id"], "source_id"),
        "content_digest": document["content_digest"],
        "license_expression": license_expression,
        "decision": decision,
        "training_allowed": decision == "CALLER_DECLARED" and training == "ALLOW",
        "redistribution_allowed": decision == "CALLER_DECLARED" and redistribution == "ALLOW",
        "attribution_required": attribution,
        "notice_digest": notice,
        "contract_restrictions": restrictions,
        "territories": territories,
        "purposes": purposes,
        "legal_review_status": "NOT_RUN",
        "license_scan_status": "NOT_RUN",
    }
    return _base_result(skill, values, scope, rights, rights=rights)


def build_ingestion_handlers(
    catalog: CatalogView, store: FoundryStore | None = None
) -> dict[str, LocalHandler]:
    """Build six exact callables; no name-derived fallback is available."""

    del store
    handlers: dict[str, LocalHandler] = {
        "api-contract-ingestion": _api_contract,
        "database-metadata-ingestion": _database_metadata,
        "license-and-rights-classification": _rights,
        "repository-incremental-ingestion": _repository_incremental,
        "runtime-trace-ingestion": _runtime_trace,
        "source-freshness-and-expiry": _freshness,
    }
    if set(handlers) != INGESTION_SEMANTIC_SKILLS:
        raise RuntimeError("ingestion semantic handler registry is not exact")
    if missing := sorted(INGESTION_SEMANTIC_SKILLS - set(catalog.atomic_skills)):
        raise RuntimeError(f"ingestion semantic Skills are absent from catalog: {missing}")
    return handlers


__all__ = ["INGESTION_SEMANTIC_SKILLS", "build_ingestion_handlers"]
