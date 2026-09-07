"""Exhaustive, deterministic implementation gaps for the exact Foundry catalog.

This is an engineering inventory, not an execution receipt or a readiness gate.
Source contracts are data. A callable local binding proves only that bounded
code is present; it cannot establish whole-Skill implementation or verification.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import heapq
import json
from typing import Any

from .canonical import canonical_digest, canonical_value
from .external_bindings import exact_external_binding
from .local_semantics import LocalHandler, LocalSemanticRuntime
from .skills import CATALOG_SCHEMA_VERSION, EXPECTED_PACKAGE, EXPECTED_PIPELINES


SCHEMA_VERSION = "elmos.foundry.implementation-readiness.v2"
EXPECTED_ATOMIC_COUNT = 1_310
EXPECTED_PACK_COUNT = 41
EXPECTED_DEPENDENCY_COUNT = 9_090
MAX_CATALOG_BYTES = 32 * 1024 * 1024


class ReadinessValidationError(ValueError):
    """An incomplete catalog or stale binding must not produce a report."""


@dataclass
class _CatalogView:
    content_sha256: str
    discovery: Mapping[str, Any]
    atomic_skills: Mapping[str, Mapping[str, Any]]
    meta_skills: Mapping[str, Mapping[str, Any]]


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ReadinessValidationError(f"{label} must be a string-keyed object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ReadinessValidationError(f"{label} must be non-empty canonical text")
    return value


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ReadinessValidationError(f"{label} must be an array")
    result = tuple(_text(item, label) for item in value)
    if len(set(result)) != len(result):
        raise ReadinessValidationError(f"{label} contains duplicate entries")
    return result


def _records(value: Any, count: int, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ReadinessValidationError(f"{label} must contain exactly {count} records")
    records: dict[str, Mapping[str, Any]] = {}
    for item in value:
        row = _object(item, label)
        name = _text(row.get("name"), f"{label}.name")
        if name in records:
            raise ReadinessValidationError(f"{label} contains duplicate identity: {name}")
        records[name] = row
    return records


def _unbound_paths(value: Any, prefix: str) -> list[str]:
    if isinstance(value, Mapping):
        return [
            path
            for key in sorted(value)
            for path in _unbound_paths(value[key], f"{prefix}.{key}")
        ]
    if isinstance(value, (list, tuple)):
        return [
            path
            for index, child in enumerate(value)
            for path in _unbound_paths(child, f"{prefix}[{index}]")
        ]
    return [prefix] if value == "UNBOUND" else []


def _dependency_order(
    records: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], dict[str, tuple[str, ...]], dict[str, int]]:
    dependencies = {
        name: _strings(row.get("dependencies"), f"{name}.dependencies")
        for name, row in records.items()
    }
    if sum(map(len, dependencies.values())) != EXPECTED_DEPENDENCY_COUNT:
        raise ReadinessValidationError("source dependency count must remain exactly 9090")
    outgoing: dict[str, list[str]] = {name: [] for name in records}
    for name, values in dependencies.items():
        for dependency in values:
            if dependency not in records:
                raise ReadinessValidationError(f"{name}: unknown dependency {dependency}")
            outgoing[dependency].append(name)
    remaining = {name: len(values) for name, values in dependencies.items()}
    ready = [name for name, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    stages: dict[str, int] = {}
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        stages[name] = max((stages[item] + 1 for item in dependencies[name]), default=0)
        for dependent in outgoing[name]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(order) != len(records):
        raise ReadinessValidationError("source dependency graph contains a cycle")
    return order, dependencies, stages


def _handler_identity(handler: LocalHandler) -> str:
    if not callable(handler):
        raise ReadinessValidationError("semantic registry contains a non-callable binding")
    module = getattr(handler, "__module__", None)
    name = getattr(handler, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(name, str):
        raise ReadinessValidationError("semantic registry handler identity is unavailable")
    return f"{module}.{name}"


def _catalog_digest(catalog: Mapping[str, Any]) -> str:
    # Catalogs are verified source JSON, not 1 MiB invocation payloads. Keep the
    # same canonical JSON encoding without recursively normalizing every source
    # string again. The CLI separately verifies the pinned raw catalog bytes.
    try:
        encoded = json.dumps(
            dict(catalog), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReadinessValidationError(f"catalog is not bounded source JSON: {exc}") from exc
    if len(encoded) > MAX_CATALOG_BYTES:
        raise ReadinessValidationError("catalog exceeds the 32 MiB inventory bound")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_readiness(
    catalog: Mapping[str, Any],
    *,
    semantic_bindings: Mapping[str, LocalHandler] | None = None,
) -> dict[str, Any]:
    """Inventory all exact catalog rows without executing a Skill or provider.

    The command-line caller additionally verifies the pinned catalog and source
    archive through ``load_compiled_catalog``. An optional observed registry is
    checked against the actual repository registry; it cannot promote a Skill.
    """
    root = _object(catalog, "catalog")
    if root.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ReadinessValidationError("unsupported compiled catalog schema")
    if root.get("package") != EXPECTED_PACKAGE:
        raise ReadinessValidationError("catalog does not identify the pinned v3 package")
    records = _records(root.get("atomic_skills"), EXPECTED_ATOMIC_COUNT, "atomic_skills")
    metas = _records(root.get("meta_skills"), EXPECTED_PACK_COUNT, "meta_skills")
    pipelines = _records(root.get("pipelines"), len(EXPECTED_PIPELINES), "pipelines")
    if set(pipelines) != EXPECTED_PIPELINES:
        raise ReadinessValidationError("pipeline identities differ from the exact source set")
    if any(row.get("execution_mode") != "PREPARE_ONLY" for row in pipelines.values()):
        raise ReadinessValidationError("pipeline inventory cannot assert runtime execution")
    packs = {_text(row.get("pack"), f"{name}.pack") for name, row in records.items()}
    if len(packs) != EXPECTED_PACK_COUNT:
        raise ReadinessValidationError("atomic Skills must cover exactly 41 packs")
    for pack in sorted(packs):
        meta = metas.get(f"elmos-{pack}")
        if meta is None or meta.get("pack") != pack:
            raise ReadinessValidationError(f"{pack}: missing or mismatched exact Meta-Skill")
        expected = {name for name, row in records.items() if row["pack"] == pack}
        if set(_strings(meta.get("candidates"), f"{pack}.candidates")) != expected:
            raise ReadinessValidationError(f"{pack}: candidate identities are incomplete or foreign")
    order, dependencies, stages = _dependency_order(records)
    catalog_digest = _catalog_digest(root)
    view = _CatalogView(
        catalog_digest.removeprefix("sha256:"),
        _object(root.get("discovery"), "discovery"),
        records,
        metas,
    )
    runtime_handlers = LocalSemanticRuntime(view).handlers
    observed_handlers = runtime_handlers if semantic_bindings is None else semantic_bindings
    if set(observed_handlers) != set(runtime_handlers):
        raise ReadinessValidationError("observed semantic registry is missing, extra, or stale")
    for name, handler in observed_handlers.items():
        if _handler_identity(handler) != _handler_identity(runtime_handlers[name]):
            raise ReadinessValidationError(f"{name}: semantic callable identity is stale or mismatched")
    local_names = set(runtime_handlers)
    external_bindings = {
        name: exact_external_binding(name, records[name])
        for name in sorted(set(records) - local_names)
    }
    registry_identities = {
        name: _handler_identity(runtime_handlers[name]) for name in sorted(runtime_handlers)
    }
    for name, row in records.items():
        expected_state = "LOCAL" if name in local_names else "PREPARE_ONLY"
        expected_binding = f"local.{name}" if name in local_names else "UNBOUND"
        if row.get("capability_state") != expected_state:
            raise ReadinessValidationError(f"{name}: catalog capability state differs from runtime")
        if row.get("semantic_handler_binding") != expected_binding:
            raise ReadinessValidationError(f"{name}: catalog semantic binding differs from runtime")
        if row.get("external_evidence_status") != "NOT_RUN":
            raise ReadinessValidationError(f"{name}: inventory cannot assert external execution")
        if row.get("certification_status") != "NOT_CERTIFIED":
            raise ReadinessValidationError(f"{name}: inventory cannot assert certification")
    transitive_missing: dict[str, set[str]] = {}
    for name in order:
        missing: set[str] = set()
        for dependency in dependencies[name]:
            missing.update(transitive_missing[dependency])
            if dependency not in local_names:
                missing.add(dependency)
        transitive_missing[name] = missing

    rows: list[dict[str, Any]] = []
    for name in sorted(records):
        row = records[name]
        activation = _object(row.get("activation_contract"), f"{name}.activation_contract")
        unbound_contracts = {
            field: _unbound_paths(row.get(field), field)
            for field in (
                "input_contracts", "output_contracts", "tool_contract", "dependency_semantics",
                "execution_contract", "compatibility_contract", "evidence_contract",
                "rollback_contract",
            )
        }
        required_gates = _strings(row.get("required_gates"), f"{name}.required_gates")
        inputs = _strings(row.get("inputs"), f"{name}.inputs")
        outputs = _strings(row.get("outputs"), f"{name}.outputs")
        tools = _strings(row.get("allowed_tools"), f"{name}.allowed_tools")
        workflow = _strings(row.get("workflow"), f"{name}.workflow")
        corpus_requirements: dict[str, int] = {}
        for category in ("positive", "negative", "ambiguous", "adversarial"):
            count = activation.get(f"{category}_required")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ReadinessValidationError(f"{name}: invalid {category} corpus requirement")
            corpus_requirements[category] = count
        direct_missing = sorted(set(dependencies[name]) - local_names)
        external = external_bindings.get(name)
        integration_binding = (
            {
                "status": "LOCAL_EXECUTABLE",
                "adapter_id": f"local.{name}",
                "route_id": None,
                "operation": "execute",
            }
            if external is None
            else {
                "status": "HOST_ROUTE_BOUND",
                "adapter_id": external[0].adapter_id,
                "adapter_digest": external[0].digest,
                "effect_class": external[0].effect_class.value,
                "route_id": external[1].route_id,
                "route_digest": external[1].digest,
                "operation": external[1].operation,
                "provider_status": "NOT_CONFIGURED",
            }
        )
        rows.append({
            "name": name,
            "pack": row["pack"],
            "version": row["version"],
            "priority": row["priority"],
            "owner": row["owner"],
            "risk_class": row["risk_class"],
            "source_path": row["source_path"],
            "source_sha256": row["source_sha256"],
            "description": row["description"],
            "workflow": list(workflow),
            "inputs": list(inputs),
            "outputs": list(outputs),
            "allowed_tools": list(tools),
            "required_gates": list(required_gates),
            "capability_state": row["capability_state"],
            "semantic_handler_binding": row["semantic_handler_binding"],
            "semantic_callable": registry_identities.get(name),
            "integration_binding": integration_binding,
            "local_evidence_status": "NOT_EVALUATED_BY_THIS_INVENTORY",
            "whole_skill_complete": False,
            "execution_authorized": False,
            "dependency_stage": stages[name],
            "dependencies": list(dependencies[name]),
            "dependency_blockers": {
                "direct_missing_semantic_handlers": direct_missing,
                "transitive_missing_semantic_handlers": sorted(transitive_missing[name]),
                "whole_dependency_contract_verification": "NOT_RUN",
            },
            "code_missing": {
                "exact_semantic_handler": name not in local_names,
                "unbound_source_contract_fields": unbound_contracts,
                "declared_tool_bindings": {
                    "tools": list(tools),
                    "status": (
                        "LOCAL_HANDLER_BOUND"
                        if external is None
                        else "EXACT_HOST_ROUTE_BOUND_PROVIDER_NOT_CONFIGURED"
                    ),
                },
                "whole_skill_workflow_coverage": "NOT_ESTABLISHED",
            },
            "verification_missing": {
                "required_gates": [{"gate": gate, "status": "NOT_RUN"} for gate in required_gates],
                "source_acceptance_corpus": {
                    "required_counts": corpus_requirements,
                    "split": activation.get("split"),
                    "embedded_in_source": activation.get("corpus_embedded"),
                    "status": "NOT_RUN",
                },
                "external_runtime": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "rollback_rehearsal": "NOT_RUN",
            },
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        })
    aggregates = []
    for pack in sorted(packs):
        members = [row for row in rows if row["pack"] == pack]
        local_count = sum(row["capability_state"] == "LOCAL" for row in members)
        aggregates.append({
            "pack": pack,
            "atomic_skills": len(members),
            "local_semantic_handlers": local_count,
            "prepare_only": len(members) - local_count,
            "whole_skills_complete": 0,
            "skills_with_missing_dependency_handlers": sum(
                bool(row["dependency_blockers"]["direct_missing_semantic_handlers"])
                for row in members
            ),
        })
    blocker_counts = Counter(
        dependency for row in rows
        for dependency in row["dependency_blockers"]["direct_missing_semantic_handlers"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "package": canonical_value(root["package"]),
        "catalog_content_digest": catalog_digest,
        "semantic_registry_digest": canonical_digest(registry_identities),
        "authority": canonical_value(root.get("authority")),
        "status": "INCOMPLETE",
        "scope": "Repository code and source-contract inventory; no Skill or provider execution",
        "summary": {
            "atomic_skills": len(rows),
            "packs": len(packs),
            "dependency_edges": sum(map(len, dependencies.values())),
            "pipelines": len(pipelines),
            "local_semantic_handlers": len(local_names),
            "prepare_only": len(rows) - len(local_names),
            "exact_adapter_bindings": len(rows),
            "host_route_bound": len(external_bindings),
            "integration_unbound": 0,
            "whole_skills_complete": 0,
            "source_acceptance_cases_required": sum(
                sum(row["verification_missing"]["source_acceptance_corpus"]["required_counts"].values())
                for row in rows
            ),
        },
        "packs": aggregates,
        "implementation_order": order,
        "implementation_frontier": [
            name for name in order if name not in local_names
            and not (set(dependencies[name]) - local_names)
        ],
        "highest_fanout_missing_handlers": [
            {"name": name, "direct_dependents": count}
            for name, count in sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "skills": rows,
        "pipeline_states": [
            {"name": name, "execution_mode": pipelines[name]["execution_mode"],
             "runtime_execution_mode": "HOST_BROKER",
             "integration_binding_status": "HOST_ROUTE_BOUND",
             "adapter_id": f"pipeline.{name}",
             "route_id": f"pipeline-route.{name}",
             "whole_pipeline_complete": False, "external_evidence_status": "NOT_RUN"}
            for name in sorted(pipelines)
        ],
        "external_evidence_status": "NOT_RUN",
        "independent_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact human index; the JSON retains every exact Skill gap."""
    summary = report["summary"]
    lines = [
        "# Foundry implementation matrix", "",
        "Generated by `tooling/report_foundry_readiness.py --write`. "
        "Do not edit this generated report directly.", "",
        f"The exact catalog contains **{summary['atomic_skills']:,} atomic Skills**, "
        f"**{summary['packs']} packs**, and **{summary['dependency_edges']:,} dependency edges**. "
        f"**{summary['local_semantic_handlers']}** Skills have bounded local semantic handlers; "
        f"**{summary['prepare_only']:,}** remain `PREPARE_ONLY` and lack exact semantic code. "
        f"All **{summary['exact_adapter_bindings']:,}** identities are integration-bound: "
        f"**{summary['host_route_bound']:,}** use distinct fail-closed host routes and "
        f"**{summary['integration_unbound']}** are route-unbound. "
        "No whole-Skill completion or production readiness is established.", "",
        "`IMPLEMENTATION_MATRIX.json` records every exact identity, source description, workflow, "
        "inputs, outputs, tools, gates, callable binding, unresolved contract fields, and direct "
        "and transitive dependency blockers. `integration_binding`, `code_missing` and "
        "`verification_missing` are separate. "
        "A local handler does not resolve an unbound whole-Skill contract or verify a source gate.", "",
        f"Source acceptance contracts require **{summary['source_acceptance_cases_required']:,} "
        "case slots** across positive, negative, ambiguous, and adversarial corpora. These are "
        "requirements, not executed test cases. External runtime and independent evidence "
        "remain `NOT_RUN`; certification remains `NOT_CERTIFIED`.", "",
        "| Pack | Skills | Local handlers | Prepare only | Missing dependency handlers |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for pack in report["packs"]:
        lines.append(
            f"| {pack['pack']} | {pack['atomic_skills']} | {pack['local_semantic_handlers']} "
            f"| {pack['prepare_only']} | {pack['skills_with_missing_dependency_handlers']} |"
        )
    lines.extend(["", "Highest-fanout missing semantic handlers:", ""])
    for blocker in report["highest_fanout_missing_handlers"][:10]:
        lines.append(f"- `{blocker['name']}`: {blocker['direct_dependents']} direct dependents.")
    lines.extend([
        "", "The JSON `implementation_order` preserves the source DAG. "
        "`implementation_frontier` identifies missing handlers whose direct dependencies have "
        "local handlers; it grants no execution or release authority.", "",
        f"Catalog content: `{report['catalog_content_digest']}`. "
        f"Semantic registry: `{report['semantic_registry_digest']}`.", "",
    ])
    return "\n".join(lines)
