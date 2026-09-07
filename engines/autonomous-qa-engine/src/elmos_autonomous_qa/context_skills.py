"""Exact local operations for autonomous-QA context and planning Skills.

The source Skill archive is specification input only.  This module implements
bounded repository-owned behavior and never executes repository code, source
package tools, generated commands, environment operations, or provider calls.
Operations that require a semantic model, native emitter, data materializer,
or environment provider retain that boundary explicitly in their result.
"""

from __future__ import annotations

import base64
import hashlib
import math
import re
from collections import defaultdict, deque
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from .canonical import canonical_json_bytes
from .contracts import (
    ContractError,
    digest_bytes,
    digest_json,
    require_exact_text,
    require_resource_id,
    require_text,
    strict_json,
)
from .domain import validate_test_dsl


MAX_ITEMS = 10_000
MAX_SENTENCES = 5_000
MAX_DIMENSION_ROWS = 256
MAX_PLANNED_CASES = 10_000
MAX_DATASET_ROWS = 1_000
MAX_DATASET_BYTES = 4 * 1024 * 1024
PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
NODE_KINDS = frozenset(
    {
        "REQUIREMENT",
        "CONSTRAINT",
        "UXR",
        "NFR",
        "AC",
        "FEATURE",
        "API",
        "PAGE",
        "DATA",
        "EVENT",
        "CODE",
        "TEST",
        "TEST_FILE",
        "DEFECT",
        "PATCH",
        "EVIDENCE",
        "OUTPUT_BUNDLE",
    }
)
EDGE_KINDS = frozenset(
    {
        "depends_on",
        "derived_from",
        "implements",
        "exposes",
        "reads",
        "writes",
        "emits",
        "consumes",
        "verifies",
        "fails_with",
        "fixed_by",
        "evidenced_by",
        "materialized_as",
        "contains",
        "supersedes",
    }
)
NATURAL_REQUIREMENT_MARKERS = re.compile(
    r"\b(?:must|shall|should|required to|may not|must not|shall not)\b|"
    r"必须|应当|不得|禁止|不允许|需要",
    re.IGNORECASE,
)
NEGATIVE_MARKERS = re.compile(
    r"\b(?:must not|shall not|may not|never|forbid(?:den)?)\b|"
    r"不得|禁止|不允许|不可",
    re.IGNORECASE,
)
QUANTIFIED_CONSTRAINT = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec(?:onds?)?|minutes?|hours?|days?|%|"
    r"bytes?|kb|mb|gb|requests?/s|rps|qps)\b|"
    r"\d+(?:\.\d+)?\s*(?:毫秒|秒|分钟|小时|天|百分比)",
    re.IGNORECASE,
)
SAFE_NETWORK_TARGET = re.compile(
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::[1-9][0-9]{0,4})?"
)
SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
SECRET_KEY = re.compile(
    r"(?:^|[_-])(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)(?:$|[_-])",
    re.IGNORECASE,
)


def _exact_fields(
    value: Mapping[str, Any],
    *,
    field: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> None:
    if any(type(key) is not str for key in value):
        raise ContractError(f"{field} keys must be exact strings")
    unexpected = sorted(set(value).difference(allowed))
    missing = sorted(required.difference(value))
    if unexpected:
        raise ContractError(f"{field} contains unsupported fields: {unexpected}")
    if missing:
        raise ContractError(f"{field} is missing required fields: {missing}")


def _objects(value: Any, field: str, *, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a{' non-empty' if not allow_empty else ''} object array")
    if len(value) > MAX_ITEMS or any(not isinstance(item, Mapping) for item in value):
        raise ContractError(f"{field} is invalid or exceeds the item limit")
    return list(value)


def _strings(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
    maximum: int = 2048,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a{' non-empty' if not allow_empty else ''} string array")
    if len(value) > MAX_ITEMS:
        raise ContractError(f"{field} exceeds the item limit")
    result = [require_text(item, f"{field}[]", maximum=maximum) for item in value]
    if len(set(result)) != len(result):
        raise ContractError(f"{field} may not contain duplicates")
    return result


def _number(
    value: Any,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not minimum <= float(value) <= maximum
    ):
        raise ContractError(f"{field} must be a finite number from {minimum} to {maximum}")
    return float(value)


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ContractError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _digest(value: Any, field: str) -> str:
    text = require_text(value, field, maximum=80)
    if SHA256.fullmatch(text) is None:
        raise ContractError(f"{field} must be a SHA-256 digest")
    return "sha256:" + text.removeprefix("sha256:")


def _stable_id(prefix: str, value: Any, *, width: int = 24) -> str:
    return f"{prefix}-{digest_json(value)[7:7 + width]}"


def _split_natural_text(text: str) -> list[str]:
    pieces = re.split(r"(?:\r?\n)+|(?<=[.!?。！？；;])\s*", text)
    result: list[str] = []
    for piece in pieces:
        normalized = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", piece).strip()
        if normalized:
            result.append(normalized)
        if len(result) > MAX_SENTENCES:
            raise ContractError("natural-language specification exceeds the sentence limit")
    return result


def _constraint_tags(statement: str) -> list[str]:
    lowered = statement.casefold()
    tags: set[str] = set()
    if QUANTIFIED_CONSTRAINT.search(statement):
        tags.add("quantified")
    if any(token in lowered for token in ("latency", "throughput", "performance", "rps", "qps", "延迟", "吞吐", "性能")):
        tags.add("performance")
    if any(token in lowered for token in ("role", "permission", "authorize", "tenant", "权限", "角色", "租户")):
        tags.add("permission")
    if any(token in lowered for token in ("compatible", "version", "browser", "device", "兼容", "版本", "浏览器", "设备")):
        tags.add("compatibility")
    if any(token in lowered for token in ("within", "before", "after", "timeout", "deadline", "之内", "之前", "之后", "超时")):
        tags.add("time")
    return sorted(tags)


def _conflict_identity(statement: str) -> str:
    lowered = statement.casefold()
    lowered = NEGATIVE_MARKERS.sub(" ", lowered)
    lowered = NATURAL_REQUIREMENT_MARKERS.sub(" ", lowered)
    lowered = re.sub(r"\bnot\b|不", " ", lowered)
    lowered = re.sub(r"[^\w\u3400-\u9fff]+", " ", lowered)
    return " ".join(lowered.split())


def _structured_requirement(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    _exact_fields(
        raw,
        field=f"requirements[{index}]",
        allowed=frozenset(
            {
                "requirement_id",
                "title",
                "statement",
                "priority",
                "required",
                "source_refs",
                "acceptance_criteria",
                "kind",
                "status",
                "actor",
                "action",
                "object",
                "preconditions",
                "postconditions",
                "data_classification",
                "business_invariants",
                "conflict_key",
                "polarity",
            }
        ),
        required=frozenset(
            {"requirement_id", "statement", "priority", "required", "source_refs"}
        ),
    )
    requirement_id = require_resource_id(raw.get("requirement_id"), "requirement_id")
    priority = require_text(raw.get("priority"), "requirement.priority")
    if priority not in PRIORITIES:
        raise ContractError("requirement.priority is invalid")
    required = raw.get("required")
    if not isinstance(required, bool):
        raise ContractError("requirement.required must be boolean")
    statement = require_exact_text(raw.get("statement"), "requirement.statement", maximum=16_384)
    acceptance = _strings(
        raw.get("acceptance_criteria", []),
        "acceptance_criteria",
        allow_empty=True,
        maximum=8192,
    )
    status = require_text(raw.get("status", "ready"), "requirement.status")
    if status not in {"ready", "ambiguous", "conflicting", "blocked", "deprecated"}:
        raise ContractError("requirement.status is invalid")
    polarity = require_text(
        raw.get("polarity", "prohibit" if NEGATIVE_MARKERS.search(statement) else "require"),
        "requirement.polarity",
    )
    if polarity not in {"require", "prohibit"}:
        raise ContractError("requirement.polarity must be require or prohibit")
    return {
        "requirement_id": requirement_id,
        "title": require_text(raw.get("title", statement[:160]), "requirement.title", maximum=512),
        "statement": statement,
        "kind": require_text(raw.get("kind", "REQ"), "requirement.kind", maximum=64),
        "priority": priority,
        "required": required,
        "source_refs": _strings(raw.get("source_refs"), "source_refs", maximum=1024),
        "acceptance_criteria": acceptance,
        "actor": require_text(raw.get("actor", "unspecified"), "requirement.actor", maximum=256),
        "action": require_text(raw.get("action", "unspecified"), "requirement.action", maximum=1024),
        "object": require_text(raw.get("object", "unspecified"), "requirement.object", maximum=1024),
        "preconditions": _strings(raw.get("preconditions", []), "preconditions", allow_empty=True),
        "postconditions": _strings(raw.get("postconditions", []), "postconditions", allow_empty=True),
        "data_classification": require_text(
            raw.get("data_classification", "unspecified"),
            "requirement.data_classification",
            maximum=64,
        ),
        "business_invariants": _strings(
            raw.get("business_invariants", []),
            "business_invariants",
            allow_empty=True,
            maximum=8192,
        ),
        "constraint_tags": _constraint_tags(statement),
        "conflict_key": require_text(
            raw.get("conflict_key", _conflict_identity(statement)),
            "requirement.conflict_key",
            maximum=2048,
        ),
        "polarity": polarity,
        "confidence": 1.0,
        "normalization_method": "STRUCTURED_EXACT",
        "status": status,
    }


def _natural_requirement(
    *, source_id: str, source_ref: str, sentence: str, ordinal: int, defaults: Mapping[str, Any]
) -> dict[str, Any]:
    polarity = "prohibit" if NEGATIVE_MARKERS.search(sentence) else "require"
    condition = ""
    body = sentence
    condition_match = re.match(
        r"\s*(?:if|when|unless|如果|当)(.+?)(?:,|，|then|则)(.+)$",
        sentence,
        re.IGNORECASE,
    )
    if condition_match:
        condition = condition_match.group(1).strip()
        body = condition_match.group(2).strip()
    marker = NATURAL_REQUIREMENT_MARKERS.search(body)
    if marker:
        actor = body[: marker.start()].strip(" ,，:") or "unspecified"
        action = body[marker.end() :].strip(" ,，:") or "unspecified"
    else:
        actor = "unspecified"
        action = "unspecified"
    explicit_acceptance = sentence.casefold().startswith(("ac:", "acceptance:")) or (
        "given" in sentence.casefold()
        and "when" in sentence.casefold()
        and "then" in sentence.casefold()
    )
    requirement_id = _stable_id(
        "REQ",
        {"source_id": source_id, "ordinal": ordinal, "statement": sentence},
        width=20,
    )
    priority = require_text(defaults.get("priority", "P2"), "document.priority")
    if priority not in PRIORITIES:
        raise ContractError("document priority is invalid")
    required = defaults.get("required", True)
    if not isinstance(required, bool):
        raise ContractError("document.required must be boolean")
    status = "ambiguous" if marker is None or not explicit_acceptance else "ready"
    return {
        "requirement_id": requirement_id,
        "title": sentence[:160],
        "statement": sentence,
        "kind": require_text(defaults.get("kind", "REQ"), "document.kind", maximum=64),
        "priority": priority,
        "required": required,
        "source_refs": [source_ref],
        "acceptance_criteria": [sentence] if explicit_acceptance else [],
        "actor": actor,
        "action": action,
        "object": action,
        "preconditions": [condition] if condition else [],
        "postconditions": [],
        "data_classification": "unspecified",
        "business_invariants": [],
        "constraint_tags": _constraint_tags(sentence),
        "conflict_key": _conflict_identity(sentence),
        "polarity": polarity,
        "confidence": 0.65 if marker else 0.25,
        "normalization_method": "BOUNDED_DETERMINISTIC_TEXT",
        "status": status,
    }


def normalize_specification(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Normalize structured requirements and bounded explicit text fragments.

    Deterministic text extraction is intentionally not represented as trusted
    semantic understanding.  Any natural-language input keeps the operation at
    ``PARTIAL`` until a separately trusted semantic normalizer resolves its
    ambiguities and acceptance criteria.
    """

    _exact_fields(
        inputs,
        field="specification input",
        allowed=frozenset({"documents", "requirements", "_runtime_context"}),
    )
    documents = _objects(inputs.get("documents", []), "documents", allow_empty=True)
    structured = _objects(inputs.get("requirements", []), "requirements", allow_empty=True)
    if not documents and not structured:
        raise ContractError("documents or requirements must be supplied")

    requirements: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(structured):
        item = _structured_requirement(raw, index)
        if item["requirement_id"] in seen_ids:
            raise ContractError(f"duplicate requirement_id: {item['requirement_id']}")
        seen_ids.add(item["requirement_id"])
        requirements.append(item)

    natural_used = False
    for document_index, document in enumerate(documents):
        _exact_fields(
            document,
            field=f"documents[{document_index}]",
            allowed=frozenset({"source_id", "source_ref", "text", "priority", "required", "kind"}),
            required=frozenset({"source_id", "source_ref", "text"}),
        )
        source_id = require_resource_id(document.get("source_id"), "document.source_id")
        source_ref = require_text(document.get("source_ref"), "document.source_ref", maximum=1024)
        text = require_exact_text(document.get("text"), "document.text", maximum=1_000_000)
        for ordinal, sentence in enumerate(_split_natural_text(text), start=1):
            natural_used = True
            item = _natural_requirement(
                source_id=source_id,
                source_ref=f"{source_ref}#segment-{ordinal}",
                sentence=sentence,
                ordinal=ordinal,
                defaults=document,
            )
            if item["requirement_id"] in seen_ids:
                raise ContractError(f"generated requirement_id collision: {item['requirement_id']}")
            seen_ids.add(item["requirement_id"])
            requirements.append(item)
            if len(requirements) > MAX_ITEMS:
                raise ContractError("normalized requirement count exceeds the item limit")

    conflict_buckets: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"require": [], "prohibit": []}
    )
    for item in requirements:
        if item["conflict_key"]:
            conflict_buckets[item["conflict_key"]][item["polarity"]].append(
                item["requirement_id"]
            )
    conflict_groups: list[dict[str, Any]] = []
    conflicting_ids: set[str] = set()
    for key, values in sorted(conflict_buckets.items()):
        if values["require"] and values["prohibit"]:
            members = sorted(values["require"] + values["prohibit"])
            conflicting_ids.update(members)
            conflict_groups.append(
                {
                    "conflict_id": _stable_id("conflict", {"key": key, "members": members}),
                    "conflict_key": key,
                    "requirement_ids": members,
                    "diagnosis": "OPPOSING_REQUIRED_POLARITY",
                    "resolution": "NOT_RUN",
                }
            )

    blocking_ids: list[str] = []
    ambiguity_records: list[dict[str, str]] = []
    for item in requirements:
        reasons: list[str] = []
        if item["requirement_id"] in conflicting_ids:
            item["status"] = "conflicting"
            reasons.append("CONFLICTING_STATEMENT")
        if item["required"] and not item["acceptance_criteria"]:
            reasons.append("ACCEPTANCE_CRITERIA_MISSING")
        if item["required"] and item["status"] != "ready":
            reasons.append("REQUIREMENT_NOT_READY")
        if item["normalization_method"] == "BOUNDED_DETERMINISTIC_TEXT":
            reasons.append("TRUSTED_SEMANTIC_NORMALIZER_REQUIRED")
        if reasons:
            if item["required"]:
                blocking_ids.append(item["requirement_id"])
            ambiguity_records.append(
                {
                    "requirement_id": item["requirement_id"],
                    "reasons": ",".join(sorted(set(reasons))),
                }
            )

    state = "PARTIAL" if blocking_ids or natural_used else "SUCCEEDED"
    return {
        "state": state,
        "code": "SPECIFICATION_REQUIRES_SEMANTIC_REVIEW"
        if state == "PARTIAL"
        else "SPECIFICATION_NORMALIZED",
        "outputs": {
            "requirements": requirements,
            "conflict_groups": conflict_groups,
            "ambiguities": ambiguity_records,
            "blocking_requirement_ids": sorted(set(blocking_ids)),
            "normalization_digest": digest_json(requirements),
            "deterministic_extraction_performed": natural_used,
            "trusted_semantic_normalization": "NOT_RUN" if natural_used else "NOT_REQUIRED",
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED"
        if natural_used
        else "LOCAL_EXECUTED",
    }


def _normalize_graph_nodes(value: Any, field: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, node in enumerate(_objects(value, field)):
        _exact_fields(
            node,
            field=f"{field}[{index}]",
            allowed=frozenset({"node_id", "kind", "label", "source_refs", "required", "attributes", "version"}),
            required=frozenset({"node_id", "kind", "label"}),
        )
        node_id = require_resource_id(node.get("node_id"), "graph.node_id")
        if node_id in seen:
            raise ContractError(f"duplicate graph node: {node_id}")
        seen.add(node_id)
        kind = require_text(node.get("kind"), "graph.node.kind")
        if kind not in NODE_KINDS:
            raise ContractError(f"unsupported graph node kind: {kind}")
        required = node.get("required", False)
        if not isinstance(required, bool):
            raise ContractError("graph node required must be boolean")
        attributes = node.get("attributes", {})
        if not isinstance(attributes, Mapping):
            raise ContractError("graph node attributes must be an object")
        records.append(
            {
                "node_id": node_id,
                "kind": kind,
                "label": require_text(node.get("label"), "graph.node.label", maximum=1024),
                "source_refs": _strings(
                    node.get("source_refs", []), "graph.node.source_refs", allow_empty=True, maximum=1024
                ),
                "required": required,
                "attributes": strict_json(attributes, "graph.node.attributes"),
                "version": require_text(node.get("version", "1"), "graph.node.version", maximum=128),
            }
        )
    return records


def _normalize_graph_edges(
    value: Any, field: str, node_ids: set[str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(_objects(value, field, allow_empty=True)):
        _exact_fields(
            edge,
            field=f"{field}[{index}]",
            allowed=frozenset({"from", "to", "kind", "confidence", "evidence_refs", "inferred", "attributes"}),
            required=frozenset({"from", "to", "kind", "confidence", "evidence_refs", "inferred"}),
        )
        source = require_resource_id(edge.get("from"), "graph.edge.from")
        target = require_resource_id(edge.get("to"), "graph.edge.to")
        if source not in node_ids or target not in node_ids:
            raise ContractError("graph edge references an unknown node")
        kind = require_text(edge.get("kind"), "graph.edge.kind")
        if kind not in EDGE_KINDS:
            raise ContractError(f"unsupported graph edge kind: {kind}")
        key = (source, target, kind)
        if key in seen:
            raise ContractError(f"duplicate graph edge: {key}")
        seen.add(key)
        confidence = _number(edge.get("confidence"), "graph.edge.confidence", minimum=0, maximum=1)
        inferred = edge.get("inferred")
        if not isinstance(inferred, bool):
            raise ContractError("graph edge inferred must be boolean")
        evidence_refs = _strings(
            edge.get("evidence_refs"), "graph.edge.evidence_refs", allow_empty=True, maximum=1024
        )
        if inferred and not evidence_refs:
            raise ContractError("an inferred graph edge requires evidence references")
        attributes = edge.get("attributes", {})
        if not isinstance(attributes, Mapping):
            raise ContractError("graph edge attributes must be an object")
        records.append(
            {
                "from": source,
                "to": target,
                "kind": kind,
                "confidence": confidence,
                "evidence_refs": evidence_refs,
                "inferred": inferred,
                "attributes": strict_json(attributes, "graph.edge.attributes"),
            }
        )
    return sorted(records, key=lambda row: (row["from"], row["to"], row["kind"]))


def _graph_queries(
    queries: list[Mapping[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    node_ids = {node["node_id"] for node in nodes}
    outbound: dict[str, list[tuple[str, str]]] = defaultdict(list)
    inbound: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in edges:
        outbound[edge["from"]].append((edge["to"], edge["kind"]))
        inbound[edge["to"]].append((edge["from"], edge["kind"]))
    results: list[dict[str, Any]] = []
    seen_query_ids: set[str] = set()
    for index, query in enumerate(queries):
        _exact_fields(
            query,
            field=f"queries[{index}]",
            allowed=frozenset({"query_id", "start_node_id", "direction", "max_depth", "edge_kinds"}),
            required=frozenset({"query_id", "start_node_id"}),
        )
        query_id = require_resource_id(query.get("query_id"), "query.query_id")
        if query_id in seen_query_ids:
            raise ContractError(f"duplicate graph query: {query_id}")
        seen_query_ids.add(query_id)
        start = require_resource_id(query.get("start_node_id"), "query.start_node_id")
        if start not in node_ids:
            raise ContractError("graph query starts at an unknown node")
        direction = require_text(query.get("direction", "both"), "query.direction")
        if direction not in {"outbound", "inbound", "both"}:
            raise ContractError("query direction is invalid")
        max_depth = _integer(query.get("max_depth", 8), "query.max_depth", minimum=0, maximum=20)
        edge_kinds = set(
            _strings(query.get("edge_kinds", []), "query.edge_kinds", allow_empty=True)
        )
        if not edge_kinds.issubset(EDGE_KINDS):
            raise ContractError("query edge_kinds contains an unsupported kind")
        queue: deque[tuple[str, list[str], int]] = deque([(start, [start], 0)])
        visited = {start}
        matches: list[dict[str, Any]] = []
        while queue:
            current, path, depth = queue.popleft()
            matches.append({"node_id": current, "path": path})
            if depth == max_depth:
                continue
            adjacent: list[tuple[str, str]] = []
            if direction in {"outbound", "both"}:
                adjacent.extend(outbound.get(current, []))
            if direction in {"inbound", "both"}:
                adjacent.extend(inbound.get(current, []))
            for target, kind in sorted(adjacent):
                if edge_kinds and kind not in edge_kinds:
                    continue
                if target not in visited:
                    visited.add(target)
                    queue.append((target, [*path, target], depth + 1))
        results.append({"query_id": query_id, "matches": matches})
    return results


def build_traceability_graph(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build a typed, evidence-scored, versioned traceability graph."""

    _exact_fields(
        inputs,
        field="traceability input",
        allowed=frozenset({"nodes", "edges", "queries", "previous_graph", "strict_confidence", "_runtime_context"}),
        required=frozenset({"nodes", "edges"}),
    )
    nodes = _normalize_graph_nodes(inputs.get("nodes"), "nodes")
    node_ids = {node["node_id"] for node in nodes}
    edges = _normalize_graph_edges(inputs.get("edges"), "edges", node_ids)
    strict_confidence = _number(
        inputs.get("strict_confidence", 0.9), "strict_confidence", minimum=0.5, maximum=1
    )
    queries = _objects(inputs.get("queries", []), "queries", allow_empty=True)

    degrees: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        degrees[edge["from"]] += 1
        degrees[edge["to"]] += 1
    orphan_nodes = sorted(node_id for node_id, degree in degrees.items() if degree == 0)
    orphan_tests = sorted(
        node["node_id"]
        for node in nodes
        if node["kind"] == "TEST"
        and not any(edge["from"] == node["node_id"] and edge["kind"] == "verifies" for edge in edges)
    )
    low_confidence_edges = [
        {"from": edge["from"], "to": edge["to"], "kind": edge["kind"]}
        for edge in edges
        if edge["confidence"] < strict_confidence
    ]
    test_nodes = {node["node_id"]: node for node in nodes if node["kind"] == "TEST"}
    materialized_tests = {
        edge["from"]
        for edge in edges
        if edge["kind"] == "materialized_as"
        and edge["from"] in test_nodes
        and any(node["node_id"] == edge["to"] and node["kind"] == "TEST_FILE" for node in nodes)
    }
    strict_verified: set[str] = set()
    for edge in edges:
        test = test_nodes.get(edge["from"])
        if (
            edge["kind"] == "verifies"
            and test is not None
            and edge["confidence"] >= strict_confidence
            and edge["evidence_refs"]
            and test["attributes"].get("executable") is True
            and test["attributes"].get("oracle_valid") is True
            and test["node_id"] in materialized_tests
        ):
            strict_verified.add(edge["to"])
    required_nodes = {
        node["node_id"]
        for node in nodes
        if node["required"] and node["kind"] in {"REQUIREMENT", "CONSTRAINT", "UXR", "NFR", "AC"}
    }
    unmapped_required = sorted(required_nodes.difference(strict_verified))
    required_tests = {
        node["node_id"] for node in nodes if node["kind"] == "TEST" and node["required"]
    }
    unmaterialized_required_tests = sorted(required_tests.difference(materialized_tests))
    unmapped_code_nodes = sorted(
        node["node_id"]
        for node in nodes
        if node["kind"] == "CODE"
        and not any(
            edge["from"] == node["node_id"] or edge["to"] == node["node_id"]
            for edge in edges
            if edge["kind"] in {"implements", "derived_from", "verifies"}
        )
    )

    previous = inputs.get("previous_graph")
    delta = {
        "added_node_ids": sorted(node_ids),
        "removed_node_ids": [],
        "changed_node_ids": [],
        "added_edges": [f"{edge['from']}|{edge['kind']}|{edge['to']}" for edge in edges],
        "removed_edges": [],
    }
    if previous is not None:
        if not isinstance(previous, Mapping):
            raise ContractError("previous_graph must be an object")
        _exact_fields(
            previous,
            field="previous_graph",
            allowed=frozenset({"graph_id", "nodes", "edges"}),
            required=frozenset({"graph_id", "nodes", "edges"}),
        )
        require_resource_id(previous.get("graph_id"), "previous_graph.graph_id")
        previous_nodes = _normalize_graph_nodes(previous.get("nodes"), "previous_graph.nodes")
        previous_node_ids = {node["node_id"] for node in previous_nodes}
        previous_edges = _normalize_graph_edges(
            previous.get("edges"), "previous_graph.edges", previous_node_ids
        )
        current_by_id = {node["node_id"]: node for node in nodes}
        previous_by_id = {node["node_id"]: node for node in previous_nodes}
        current_edge_keys = {
            f"{edge['from']}|{edge['kind']}|{edge['to']}" for edge in edges
        }
        previous_edge_keys = {
            f"{edge['from']}|{edge['kind']}|{edge['to']}" for edge in previous_edges
        }
        delta = {
            "added_node_ids": sorted(node_ids.difference(previous_node_ids)),
            "removed_node_ids": sorted(previous_node_ids.difference(node_ids)),
            "changed_node_ids": sorted(
                node_id
                for node_id in node_ids.intersection(previous_node_ids)
                if current_by_id[node_id] != previous_by_id[node_id]
            ),
            "added_edges": sorted(current_edge_keys.difference(previous_edge_keys)),
            "removed_edges": sorted(previous_edge_keys.difference(current_edge_keys)),
        }

    graph_document = {"nodes": nodes, "edges": edges}
    blockers = sorted(
        set(unmapped_required + unmaterialized_required_tests + orphan_tests)
    )
    return {
        "state": "PARTIAL" if blockers else "SUCCEEDED",
        "code": "TRACEABILITY_GAPS" if blockers else "TRACEABILITY_GRAPH_BUILT",
        "outputs": {
            "graph_id": _stable_id("graph", graph_document, width=32),
            "nodes": nodes,
            "edges": edges,
            "strict_confidence": strict_confidence,
            "strict_executable_coverage": 1.0
            if not required_nodes
            else len(required_nodes.intersection(strict_verified)) / len(required_nodes),
            "unmapped_required": unmapped_required,
            "unmaterialized_required_tests": unmaterialized_required_tests,
            "orphan_nodes": orphan_nodes,
            "orphan_tests": orphan_tests,
            "unmapped_code_nodes": unmapped_code_nodes,
            "low_confidence_edges": low_confidence_edges,
            "delta": delta,
            "query_results": _graph_queries(queries, nodes, edges),
        },
        "implementation_state": "LOCAL_EXECUTED",
    }


def _dimension_rows(dimensions: Mapping[str, Any]) -> list[dict[str, str]]:
    if any(type(key) is not str for key in dimensions):
        raise ContractError("dimension names must be exact strings")
    keys = sorted(dimensions)
    if len(keys) > 8:
        raise ContractError("a requirement may declare at most eight dimensions")
    values: dict[str, list[str]] = {}
    for key in keys:
        normalized_key = require_resource_id(key, "dimension name")
        values[normalized_key] = _strings(
            dimensions[key], f"dimensions.{key}", maximum=256
        )
        if len(values[normalized_key]) > 16:
            raise ContractError("a dimension may contain at most sixteen values")
    keys = sorted(values)
    if not keys:
        return [{}]
    rows = [{keys[0]: value} for value in values[keys[0]]]
    for position, key in enumerate(keys[1:], start=1):
        current_values = values[key]
        for index, row in enumerate(rows):
            row[key] = current_values[index % len(current_values)]
        previous_keys = keys[:position]
        for previous_key in previous_keys:
            for previous_value in values[previous_key]:
                for current_value in current_values:
                    if any(
                        row.get(previous_key) == previous_value
                        and row.get(key) == current_value
                        for row in rows
                    ):
                        continue
                    row = {candidate: values[candidate][0] for candidate in keys[: position + 1]}
                    row[previous_key] = previous_value
                    row[key] = current_value
                    rows.append(row)
                    if len(rows) > MAX_DIMENSION_ROWS:
                        raise ContractError("pairwise dimension plan exceeds the row limit")
    return rows


def _risk_strategies(priority: str, tags: set[str]) -> list[str]:
    strategies = {"positive", "negative", "boundary"}
    if priority in {"P0", "P1"}:
        strategies.update({"state-transition", "permission-deny", "concurrency", "recovery"})
    if tags & {"api", "contract"}:
        strategies.add("api-compatibility")
    if tags & {"database", "migration"}:
        strategies.update({"transaction", "rollback"})
    if tags & {"message", "workflow"}:
        strategies.update({"duplicate", "out-of-order", "compensation"})
    if tags & {"ui", "ux"}:
        strategies.update({"ui-journey", "accessibility"})
    if tags & {"performance", "slo"}:
        strategies.add("performance-baseline")
    if tags & {"security", "tenant", "authorization"}:
        strategies.add("security-abuse")
    if tags & {"resilience", "recovery", "chaos"}:
        strategies.add("resilience")
    return sorted(strategies)


def plan_risk_coverage(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create an explainable risk, pairwise coverage, and suite plan."""

    _exact_fields(
        inputs,
        field="risk planning input",
        allowed=frozenset({"requirements", "budget", "support_matrix", "_runtime_context"}),
        required=frozenset({"requirements", "budget"}),
    )
    requirements = _objects(inputs.get("requirements"), "requirements")
    budget = inputs.get("budget")
    if not isinstance(budget, Mapping):
        raise ContractError("budget must be an object")
    _exact_fields(
        budget,
        field="budget",
        allowed=frozenset({"wall_clock_seconds", "max_compute_seconds", "max_cases"}),
        required=frozenset({"wall_clock_seconds", "max_cases"}),
    )
    wall_budget = _number(
        budget.get("wall_clock_seconds"), "budget.wall_clock_seconds", minimum=1, maximum=31_536_000
    )
    compute_budget = _number(
        budget.get("max_compute_seconds", wall_budget * 256),
        "budget.max_compute_seconds",
        minimum=1,
        maximum=31_536_000 * 256,
    )
    max_cases = _integer(budget.get("max_cases"), "budget.max_cases", minimum=1, maximum=MAX_PLANNED_CASES)
    support_matrix = inputs.get("support_matrix", {})
    if not isinstance(support_matrix, Mapping):
        raise ContractError("support_matrix must be an object")
    support_dimensions = {
        require_resource_id(key, "support_matrix key"): _strings(
            value, f"support_matrix.{key}", maximum=256
        )
        for key, value in support_matrix.items()
    }

    cases: list[dict[str, Any]] = []
    risk_records: list[dict[str, Any]] = []
    seen_requirements: set[str] = set()
    for index, requirement in enumerate(requirements):
        _exact_fields(
            requirement,
            field=f"requirements[{index}]",
            allowed=frozenset(
                {
                    "requirement_id",
                    "priority",
                    "required",
                    "risk_tags",
                    "business_impact",
                    "change_complexity",
                    "historical_defects",
                    "data_sensitivity",
                    "external_dependency",
                    "dimensions",
                    "estimated_seconds",
                }
            ),
            required=frozenset({"requirement_id", "priority", "required"}),
        )
        requirement_id = require_resource_id(requirement.get("requirement_id"), "requirement_id")
        if requirement_id in seen_requirements:
            raise ContractError(f"duplicate requirement_id: {requirement_id}")
        seen_requirements.add(requirement_id)
        priority = require_text(requirement.get("priority"), "requirement.priority")
        if priority not in PRIORITIES:
            raise ContractError("requirement priority is invalid")
        required = requirement.get("required")
        if not isinstance(required, bool):
            raise ContractError("requirement.required must be boolean")
        tags = {
            value.casefold()
            for value in _strings(requirement.get("risk_tags", []), "risk_tags", allow_empty=True)
        }
        business = _integer(requirement.get("business_impact", 3), "business_impact", minimum=0, maximum=5)
        complexity = _integer(requirement.get("change_complexity", 2), "change_complexity", minimum=0, maximum=5)
        defects = _integer(requirement.get("historical_defects", 0), "historical_defects", minimum=0, maximum=1000)
        sensitivity = require_text(requirement.get("data_sensitivity", "internal"), "data_sensitivity")
        sensitivity_weight = {"public": 0, "internal": 4, "confidential": 8, "restricted": 12}.get(sensitivity)
        if sensitivity_weight is None:
            raise ContractError("data_sensitivity is invalid")
        external = requirement.get("external_dependency", False)
        if not isinstance(external, bool):
            raise ContractError("external_dependency must be boolean")
        score = min(
            100,
            {"P0": 40, "P1": 30, "P2": 20, "P3": 10}[priority]
            + business * 6
            + complexity * 3
            + min(defects, 10) * 2
            + sensitivity_weight
            + (5 if external else 0),
        )
        band = "CRITICAL" if score >= 75 else "HIGH" if score >= 55 else "MEDIUM" if score >= 35 else "LOW"
        raw_dimensions = requirement.get("dimensions", {})
        if not isinstance(raw_dimensions, Mapping):
            raise ContractError("requirement.dimensions must be an object")
        merged_dimensions = dict(support_dimensions)
        for key, value in raw_dimensions.items():
            normalized_key = require_resource_id(key, "requirement dimension key")
            merged_dimensions[normalized_key] = _strings(value, f"dimensions.{key}", maximum=256)
        combinations = _dimension_rows(merged_dimensions)
        strategies = _risk_strategies(priority, tags)
        estimated_seconds = _number(
            requirement.get("estimated_seconds", 30),
            "estimated_seconds",
            minimum=1,
            maximum=604_800,
        )
        risk_records.append(
            {
                "requirement_id": requirement_id,
                "risk_score": score,
                "risk_band": band,
                "strategies": strategies,
                "pairwise_rows": len(combinations),
            }
        )
        for strategy in strategies:
            for combination in combinations:
                environment = (
                    "performance-isolated"
                    if strategy in {"performance-baseline"}
                    else "browser-device-isolated"
                    if strategy in {"ui-journey", "accessibility"}
                    else "chaos-isolated"
                    if strategy == "resilience"
                    else "sandbox-isolated"
                )
                case_identity = {
                    "requirement_id": requirement_id,
                    "strategy": strategy,
                    "dimensions": combination,
                }
                cases.append(
                    {
                        "planned_case_id": _stable_id("plan-case", case_identity),
                        "requirement_id": requirement_id,
                        "priority": priority,
                        "required": required,
                        "risk_score": score,
                        "risk_band": band,
                        "strategy": strategy,
                        "dimensions": combination,
                        "environment_profile": environment,
                        "data_profile": "tenant-isolated-deterministic",
                        "oracle_requirements": ["business-semantic", "no-unexpected-side-effect"],
                        "evidence_requirements": ["structured-result", "raw-runner-output", "environment-ref"],
                        "estimated_seconds": estimated_seconds,
                    }
                )
                if len(cases) > MAX_PLANNED_CASES:
                    raise ContractError("risk coverage plan exceeds the case limit")

    suite_members = {
        "pr-incremental": [
            case["planned_case_id"]
            for case in cases
            if case["priority"] in {"P0", "P1"} or case["required"]
        ],
        "nightly-full": [case["planned_case_id"] for case in cases],
        "release-certification": [
            case["planned_case_id"]
            for case in cases
            if case["required"]
            or case["strategy"] in {"performance-baseline", "security-abuse", "resilience"}
        ],
    }
    compute_seconds = math.fsum(case["estimated_seconds"] for case in cases)
    by_environment: dict[str, float] = defaultdict(float)
    for case in cases:
        by_environment[case["environment_profile"]] += case["estimated_seconds"]
    critical_path_seconds = max(by_environment.values(), default=0.0)
    blockers: list[str] = []
    if len(cases) > max_cases:
        blockers.append("REQUIRED_SCOPE_EXCEEDS_CASE_BUDGET")
    if compute_seconds > compute_budget:
        blockers.append("REQUIRED_SCOPE_EXCEEDS_COMPUTE_BUDGET")
    if critical_path_seconds > wall_budget:
        blockers.append("REQUIRED_SCOPE_EXCEEDS_WALL_CLOCK_BUDGET")
    return {
        "state": "PARTIAL" if blockers else "SUCCEEDED",
        "code": "COVERAGE_BUDGET_BLOCKED" if blockers else "RISK_COVERAGE_PLANNED",
        "outputs": {
            "risk_records": risk_records,
            "planned_cases": cases,
            "suites": suite_members,
            "combination_strategy": "DETERMINISTIC_PAIRWISE_V1",
            "environment_resource_seconds": dict(sorted(by_environment.items())),
            "estimated_compute_seconds": compute_seconds,
            "estimated_critical_path_seconds": critical_path_seconds,
            "budget": {
                "wall_clock_seconds": wall_budget,
                "max_compute_seconds": compute_budget,
                "max_cases": max_cases,
            },
            "blockers": blockers,
            "required_scope_silently_dropped": False,
            "execution": "NOT_RUN",
        },
        "implementation_state": "LOCAL_EXECUTED",
    }


def compile_test_model(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Migrate and validate the DSL, then create a native compile source map.

    The operation never claims that native source was emitted or executed.  It
    prepares exact emitter units for the adapter/materialization Skills.
    """

    _exact_fields(
        inputs,
        field="test model input",
        allowed=frozenset({"dsl_version", "target_version", "test_cases", "_runtime_context"}),
        required=frozenset({"dsl_version", "test_cases"}),
    )
    source_version = require_text(inputs.get("dsl_version"), "dsl_version", maximum=32)
    target_version = require_text(inputs.get("target_version", "1.1"), "target_version", maximum=32)
    if source_version not in {"1.0", "1.1"} or target_version != "1.1":
        raise ContractError("only deterministic DSL migration from 1.0 or 1.1 to 1.1 is supported")
    raw_cases = strict_json(inputs.get("test_cases"), "test_cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ContractError("test_cases must be a non-empty array")
    migrated_cases: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise ContractError("test_cases items must be objects")
        case = dict(raw)
        if source_version == "1.0":
            case.setdefault("risk_tags", [])
            case.setdefault("parameters", {})
            case.setdefault(
                "stability",
                {"deterministic": True, "retry_for_classification_max": 0},
            )
            case.setdefault("materialization", {"validation_status": "planned"})
        migrated_cases.append(case)
        if index >= MAX_ITEMS:
            raise ContractError("test model exceeds the case limit")
    validated = validate_test_dsl({"test_cases": migrated_cases})
    canonical_cases = validated["outputs"]["test_cases"]
    source_map: list[dict[str, Any]] = []
    compile_units: list[dict[str, Any]] = []
    blockers: list[str] = []
    for case in canonical_cases:
        test_case_id = case["test_case_id"]
        planned_paths = list(case["materialization"]["planned_paths"])
        if not planned_paths:
            blockers.append(f"{test_case_id}:NATIVE_PATH_REQUIRED")
        source_map.append(
            {
                "test_case_id": test_case_id,
                "requirement_refs": list(case["requirement_refs"]),
                "step_ids": [step["step_id"] for step in case["steps"]],
                "oracle_ids": [oracle["oracle_id"] for oracle in case["oracles"]],
                "planned_paths": planned_paths,
                "case_digest": digest_json(case),
            }
        )
        compile_units.append(
            {
                "compile_unit_id": _stable_id("compile-unit", case),
                "test_case_id": test_case_id,
                "adapter_key": case["executor"]["adapter_key"],
                "capability": case["executor"]["capability"],
                "planned_paths": planned_paths,
                "emitter_required": True,
                "native_source_generation": "NOT_RUN",
                "native_validation": "NOT_RUN",
                "native_execution": "NOT_RUN",
            }
        )
    migration = {
        "source_version": source_version,
        "target_version": target_version,
        "performed": source_version != target_version,
        "test_case_count": len(canonical_cases),
    }
    return {
        "state": "PARTIAL",
        "code": "TEST_MODEL_AWAITS_NATIVE_EMITTER"
        if not blockers
        else "TEST_MODEL_NATIVE_PATHS_INCOMPLETE",
        "outputs": {
            "dsl_version": target_version,
            "test_cases": canonical_cases,
            "dsl_digest": digest_json(canonical_cases),
            "migration": migration,
            "migration_digest": digest_json(migration),
            "source_map": source_map,
            "compile_units": compile_units,
            "blockers": blockers,
            "native_source_generation": "NOT_RUN",
            "native_execution": "NOT_RUN",
            "caller_toolchain_qualification_accepted": False,
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


def _synthetic_field_value(
    field: Mapping[str, Any], *, dataset_id: str, row_index: int, seed: str
) -> Any:
    _exact_fields(
        field,
        field="dataset.schema[]",
        allowed=frozenset({"name", "kind", "nullable", "values", "minimum", "maximum"}),
        required=frozenset({"name", "kind"}),
    )
    name = require_resource_id(field.get("name"), "dataset field name")
    kind = require_text(field.get("kind"), "dataset field kind")
    nullable = field.get("nullable", False)
    if not isinstance(nullable, bool):
        raise ContractError("dataset field nullable must be boolean")
    material = hashlib.sha256(
        f"{seed}\x00{dataset_id}\x00{row_index}\x00{name}".encode("utf-8")
    ).hexdigest()
    if nullable and row_index > 0 and int(material[:2], 16) % 11 == 0:
        return None
    if kind == "string":
        return f"{name}-{material[:16]}"
    if kind == "integer":
        minimum = field.get("minimum", 0)
        maximum = field.get("maximum", 1_000_000)
        minimum = _integer(minimum, "field.minimum", minimum=-1_000_000_000, maximum=1_000_000_000)
        maximum = _integer(maximum, "field.maximum", minimum=-1_000_000_000, maximum=1_000_000_000)
        if maximum < minimum:
            raise ContractError("integer field maximum is below minimum")
        return minimum + int(material[:16], 16) % (maximum - minimum + 1)
    if kind == "boolean":
        return int(material[:2], 16) % 2 == 0
    if kind == "decimal":
        sign = "-" if int(material[0], 16) % 2 else ""
        return f"{sign}{int(material[1:9], 16) % 1_000_000}.{int(material[9:13], 16) % 10_000:04d}"
    if kind == "timestamp":
        value = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=int(material[:12], 16) % (20 * 365 * 24 * 60 * 60)
        )
        return value.isoformat().replace("+00:00", "Z")
    if kind == "uuid":
        return f"{material[:8]}-{material[8:12]}-{material[12:16]}-{material[16:20]}-{material[20:32]}"
    if kind == "enum":
        values = _strings(field.get("values"), "field.values", maximum=512)
        return values[int(material[:8], 16) % len(values)]
    raise ContractError(f"unsupported synthetic field kind: {kind}")


def prepare_test_data(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Generate deterministic synthetic bytes and a fenced materialization plan."""

    _exact_fields(
        inputs,
        field="test data input",
        allowed=frozenset({"run_id", "seed", "lease_seconds", "datasets", "_runtime_context"}),
        required=frozenset({"run_id", "seed", "lease_seconds", "datasets"}),
    )
    run_id = require_resource_id(inputs.get("run_id"), "run_id")
    seed = require_text(inputs.get("seed"), "seed", maximum=1024)
    lease_seconds = _integer(
        inputs.get("lease_seconds"), "lease_seconds", minimum=60, maximum=86_400
    )
    datasets = _objects(inputs.get("datasets"), "datasets")
    generated: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_ids: set[str] = set()
    for index, dataset in enumerate(datasets):
        _exact_fields(
            dataset,
            field=f"datasets[{index}]",
            allowed=frozenset({"dataset_id", "source", "classification", "row_count", "schema", "generator_version"}),
            required=frozenset({"dataset_id", "source", "classification", "row_count", "schema"}),
        )
        dataset_id = require_resource_id(dataset.get("dataset_id"), "dataset_id")
        if dataset_id in seen_ids:
            raise ContractError(f"duplicate dataset_id: {dataset_id}")
        seen_ids.add(dataset_id)
        source = require_text(dataset.get("source"), "dataset.source").casefold()
        classification = require_text(dataset.get("classification"), "dataset.classification").casefold()
        if classification not in {"public", "internal", "confidential", "restricted"}:
            raise ContractError("dataset classification is invalid")
        row_count = _integer(
            dataset.get("row_count"), "dataset.row_count", minimum=1, maximum=MAX_DATASET_ROWS
        )
        schema = _objects(dataset.get("schema"), "dataset.schema")
        field_names = [require_resource_id(field.get("name"), "dataset field name") for field in schema]
        if len(set(field_names)) != len(field_names):
            raise ContractError("dataset schema contains duplicate field names")
        namespace = "qa-" + hashlib.sha256(
            f"{run_id}\x00{dataset_id}\x00{seed}".encode("utf-8")
        ).hexdigest()[:24]
        fence_token = digest_json(
            {"run_id": run_id, "dataset_id": dataset_id, "namespace": namespace, "lease_seconds": lease_seconds}
        )
        if source not in {"synthetic", "generated"}:
            blockers.append(f"{dataset_id}:TRUSTED_SANITIZATION_OR_FIXTURE_RECEIPT_REQUIRED")
            generated.append(
                {
                    "dataset_id": dataset_id,
                    "source": source,
                    "classification": classification,
                    "content_base64": None,
                    "sha256": None,
                    "byte_count": None,
                    "namespace": namespace,
                    "lease": {
                        "lease_seconds": lease_seconds,
                        "fencing_token": fence_token,
                        "acquisition": "NOT_RUN",
                    },
                    "materialization": "NOT_RUN",
                }
            )
            continue
        rows = [
            {
                field_names[field_index]: _synthetic_field_value(
                    field,
                    dataset_id=dataset_id,
                    row_index=row_index,
                    seed=seed,
                )
                for field_index, field in enumerate(schema)
            }
            for row_index in range(row_count)
        ]
        payload = canonical_json_bytes(
            {
                "schema_version": "elmos.autonomous-qa.synthetic-data.v1",
                "dataset_id": dataset_id,
                "generator_version": require_text(
                    dataset.get("generator_version", "repository-owned-v1"),
                    "dataset.generator_version",
                    maximum=128,
                ),
                "rows": rows,
            }
        )
        if len(payload) > MAX_DATASET_BYTES:
            raise ContractError("generated dataset exceeds the byte limit")
        generated.append(
            {
                "dataset_id": dataset_id,
                "source": source,
                "classification": classification,
                "row_count": row_count,
                "content_base64": base64.b64encode(payload).decode("ascii"),
                "sha256": digest_bytes(payload),
                "byte_count": len(payload),
                "namespace": namespace,
                "lease": {
                    "lease_seconds": lease_seconds,
                    "fencing_token": fence_token,
                    "acquisition": "NOT_RUN",
                },
                "cleanup_plan": {
                    "operation": "delete-namespace-if-fencing-token-matches",
                    "idempotency_key": _stable_id(
                        "cleanup", {"dataset_id": dataset_id, "fencing_token": fence_token}
                    ),
                    "performed": False,
                },
                "materialization": "NOT_RUN",
            }
        )
    blocked = bool(blockers)
    return {
        "state": "BLOCKED" if blocked else "PARTIAL",
        "code": "TEST_DATA_SOURCE_BLOCKED"
        if blocked
        else "SYNTHETIC_TEST_DATA_AWAITS_MATERIALIZATION",
        "outputs": {
            "datasets": generated,
            "seed_digest": digest_bytes(seed.encode("utf-8")),
            "blockers": blockers,
            "namespace_acquisition": "NOT_RUN",
            "data_materialization": "NOT_RUN",
            "cleanup_execution": "NOT_RUN",
            "production_data_accessed": False,
        },
        "implementation_state": "LOCAL_VALIDATED"
        if blocked
        else "EXTERNAL_ADAPTER_REQUIRED",
    }


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            SECRET_KEY.search(str(key)) is not None or _contains_secret_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def plan_environment_orchestration(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create a digest-bound environment lifecycle plan without provisioning."""

    _exact_fields(
        inputs,
        field="environment input",
        allowed=frozenset(
            {
                "environment_id",
                "profile",
                "template",
                "template_digest",
                "image_digest",
                "config",
                "resources",
                "network_allowlist",
                "secret_refs",
                "lease_seconds",
                "_runtime_context",
            }
        ),
        required=frozenset(
            {
                "environment_id",
                "profile",
                "template",
                "template_digest",
                "image_digest",
                "config",
                "resources",
                "lease_seconds",
            }
        ),
    )
    environment_id = require_resource_id(inputs.get("environment_id"), "environment_id")
    profile = require_text(inputs.get("profile"), "profile", maximum=256)
    profile_tokens = set(re.split(r"[^a-z0-9]+", profile.casefold()))
    if profile_tokens & {"production", "prod"}:
        raise ContractError("production environment profiles are forbidden")
    template = inputs.get("template")
    config = inputs.get("config")
    if not isinstance(template, Mapping) or not isinstance(config, Mapping):
        raise ContractError("template and config must be objects")
    normalized_template = strict_json(template, "environment.template")
    normalized_config = strict_json(config, "environment.config")
    if _contains_secret_key(normalized_config):
        raise ContractError("environment config contains an inline secret-like field")
    template_digest = _digest(inputs.get("template_digest"), "template_digest")
    if digest_json(normalized_template) != template_digest:
        raise ContractError("template_digest does not match the canonical template")
    image_digest = _digest(inputs.get("image_digest"), "image_digest")
    lease_seconds = _integer(
        inputs.get("lease_seconds"), "lease_seconds", minimum=60, maximum=604_800
    )
    secret_refs = _strings(
        inputs.get("secret_refs", []), "secret_refs", allow_empty=True, maximum=512
    )
    for secret_ref in secret_refs:
        require_resource_id(secret_ref, "secret_ref")
    network_allowlist = _strings(
        inputs.get("network_allowlist", []),
        "network_allowlist",
        allow_empty=True,
        maximum=512,
    )
    for target in network_allowlist:
        if target in {"*", "0.0.0.0/0", "::/0"} or SAFE_NETWORK_TARGET.fullmatch(target) is None:
            raise ContractError("network allowlist target is not exact and bounded")
        if any(token in target.casefold() for token in ("prod", "production")):
            raise ContractError("production network targets are forbidden")

    resources: list[dict[str, Any]] = []
    seen_resources: set[str] = set()
    for index, resource in enumerate(_objects(inputs.get("resources"), "resources")):
        _exact_fields(
            resource,
            field=f"resources[{index}]",
            allowed=frozenset({"resource_id", "kind", "version", "image_digest", "configuration"}),
            required=frozenset({"resource_id", "kind", "version"}),
        )
        resource_id = require_resource_id(resource.get("resource_id"), "resource_id")
        if resource_id in seen_resources:
            raise ContractError(f"duplicate environment resource: {resource_id}")
        seen_resources.add(resource_id)
        kind = require_text(resource.get("kind"), "resource.kind")
        if kind not in {"namespace", "network", "storage", "database", "message", "service", "browser", "clock"}:
            raise ContractError("environment resource kind is unsupported")
        version = require_text(resource.get("version"), "resource.version", maximum=256)
        if version.casefold() in {"latest", "stable", "main", "head", "*"}:
            raise ContractError("environment resource versions must be exact")
        resource_image = resource.get("image_digest")
        if kind in {"database", "message", "service", "browser"} and resource_image is None:
            raise ContractError(f"resource {resource_id} requires an exact image digest")
        configuration = resource.get("configuration", {})
        if not isinstance(configuration, Mapping):
            raise ContractError("resource.configuration must be an object")
        normalized_resource_config = strict_json(
            configuration, "resource.configuration"
        )
        if _contains_secret_key(normalized_resource_config):
            raise ContractError("resource configuration contains an inline secret-like field")
        resources.append(
            {
                "resource_id": resource_id,
                "kind": kind,
                "version": version,
                "image_digest": _digest(resource_image, "resource.image_digest")
                if resource_image is not None
                else None,
                "configuration": normalized_resource_config,
                "configuration_digest": digest_json(normalized_resource_config),
            }
        )

    plan_identity = {
        "environment_id": environment_id,
        "profile": profile,
        "template_digest": template_digest,
        "image_digest": image_digest,
        "config_digest": digest_json(normalized_config),
        "resources": resources,
        "network_allowlist": network_allowlist,
        "secret_refs": secret_refs,
        "lease_seconds": lease_seconds,
    }
    lease_token = digest_json(plan_identity)
    provision_steps = [
        {
            "step": index + 1,
            "operation": f"provision-{resource['kind']}",
            "resource_id": resource["resource_id"],
            "idempotency_key": _stable_id(
                "env-step", {"plan": lease_token, "resource": resource["resource_id"]}
            ),
        }
        for index, resource in enumerate(resources)
    ]
    readiness = [
        {
            "resource_id": resource["resource_id"],
            "checks": ["endpoint", "version", "schema", "clock", "resource-calibration"],
            "status": "NOT_RUN",
        }
        for resource in resources
    ]
    destroy_steps = [
        {
            "step": index + 1,
            "operation": f"destroy-{resource['kind']}",
            "resource_id": resource["resource_id"],
            "fencing_token": lease_token,
        }
        for index, resource in enumerate(reversed(resources))
    ]
    return {
        "state": "PARTIAL",
        "code": "ENVIRONMENT_PLAN_AWAITS_PROVIDER",
        "outputs": {
            "environment_plan_id": _stable_id("environment-plan", plan_identity),
            "profile": profile,
            "template_digest": template_digest,
            "image_digest": image_digest,
            "config_digest": digest_json(normalized_config),
            "resources": resources,
            "network_policy": {
                "default": "DENY",
                "allowlist": network_allowlist,
            },
            "secret_refs": secret_refs,
            "lease": {
                "lease_seconds": lease_seconds,
                "fencing_token": lease_token,
                "acquisition": "NOT_RUN",
            },
            "provision_steps": provision_steps,
            "readiness_checks": readiness,
            "destroy_steps": destroy_steps,
            "reaper_plan": {
                "scan_expired_leases": True,
                "require_fencing_token_match": True,
                "execution": "NOT_RUN",
            },
            "endpoint_allocation": "NOT_RUN",
            "provisioning": "NOT_RUN",
            "readiness_execution": "NOT_RUN",
            "destroy_execution": "NOT_RUN",
            "production_access_allowed": False,
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


__all__ = [
    "build_traceability_graph",
    "compile_test_model",
    "normalize_specification",
    "plan_environment_orchestration",
    "plan_risk_coverage",
    "prepare_test_data",
]
