"""Private deterministic primitives used only by authority-bound exact handlers.

The functions in this module are deliberately pure: they perform no file,
network, process, database, clock, random, plugin, or provider access.  They
operate only on caller-supplied typed values, enforce conservative size limits,
and return canonical, replayable summaries. Direct calls are ordinary pure
computations and never create runtime evidence, authority, or certification.
"""

from __future__ import annotations

import heapq
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import NoReturn, cast

from ..canonical import JSONLimits, canonical_json_bytes, digest_object
from ..errors import ContractError

MAX_ITEMS = 10_000
MAX_EDGES = 50_000
MAX_TOTAL_NODES = 50_000
MAX_TEXT_BYTES = 65_536
MAX_QUERY_TERMS = 64
_LIMITS = JSONLimits(
    max_bytes=2_000_000,
    max_depth=24,
    max_nodes=MAX_TOTAL_NODES,
    max_members=MAX_EDGES,
    max_string_bytes=MAX_TEXT_BYTES,
    max_key_bytes=512,
)
_DIGEST_PREFIX = "sha256:"
_KINDS = frozenset({"dataset", "table", "column"})


def _fail(message: str, code: str) -> NoReturn:
    raise ContractError(message, code=code)


def _bound(label: str, value: object) -> None:
    try:
        canonical_json_bytes(value, limits=_LIMITS)
    except ContractError as exc:
        raise ContractError(
            f"{label} exceeds the local algorithm input boundary",
            code="LOCAL_INPUT_LIMIT",
        ) from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail(f"{label} must be an object with string keys", "INVALID_LOCAL_INPUT")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        _fail(f"{label} must be an array", "INVALID_LOCAL_INPUT")
    if len(value) > MAX_ITEMS:
        _fail(f"{label} exceeds {MAX_ITEMS} items", "LOCAL_INPUT_LIMIT")
    return cast(Sequence[object], value)


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        _fail(f"{label} must be bounded text", "INVALID_LOCAL_INPUT")
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        _fail(f"{label} exceeds the text boundary", "LOCAL_INPUT_LIMIT")
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label)
    if len(result) > 200 or any(character.isspace() for character in result):
        _fail(f"{label} must be a compact identifier", "INVALID_LOCAL_INPUT")
    return result


def _digest(value: object, label: str) -> str:
    result = _text(value, label)
    if len(result) != 71 or not result.startswith(_DIGEST_PREFIX):
        _fail(f"{label} must be an exact sha256 digest", "INVALID_DIGEST")
    suffix = result.removeprefix(_DIGEST_PREFIX)
    if any(character not in "0123456789abcdef" for character in suffix):
        _fail(f"{label} must be a lowercase sha256 digest", "INVALID_DIGEST")
    return result


def _integer(value: object, label: str, *, minimum: int = 0, maximum: int = MAX_ITEMS) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        _fail(f"{label} must be an integer in [{minimum}, {maximum}]", "INVALID_LOCAL_INPUT")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{label} must be boolean", "INVALID_LOCAL_INPUT")
    return value


def _decimal(value: object, label: str, *, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        _fail(f"{label} must not use binary floating point", "INVALID_DECIMAL")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ContractError(f"{label} is not decimal", code="INVALID_DECIMAL") from exc
    else:
        _fail(f"{label} must be an integer, decimal string, or Decimal", "INVALID_DECIMAL")
    exponent = result.as_tuple().exponent
    if not isinstance(exponent, int):
        _fail(f"{label} must be finite", "INVALID_DECIMAL")
    if not result.is_finite() or len(result.as_tuple().digits) > 38 or -exponent > 18:
        _fail(f"{label} exceeds the decimal boundary", "INVALID_DECIMAL")
    if minimum is not None and result < minimum:
        _fail(f"{label} is below its minimum", "INVALID_DECIMAL")
    return result


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _exact_keys(
    value: Mapping[str, object],
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing or unknown:
        raise ContractError(
            "record keys do not match the exact local contract",
            code="INVALID_LOCAL_SCHEMA",
            details={"missing": missing, "unknown": unknown},
        )


def _text_items(value: object, label: str) -> tuple[str, ...]:
    items = tuple(_identifier(item, f"{label}[]") for item in _sequence(value, label))
    if len(items) != len(set(items)):
        _fail(f"{label} contains duplicates", "DUPLICATE_LOCAL_INPUT")
    return items


def validate_provenance_bindings(
    version_bindings: Mapping[str, object],
    dependencies: Mapping[str, object],
) -> dict[str, object]:
    """Validate exact digest bindings and an acyclic dependency closure."""

    _bound("provenance", {"version_bindings": version_bindings, "dependencies": dependencies})
    bindings = _mapping(version_bindings, "version_bindings")
    graph_input = _mapping(dependencies, "dependencies")
    if not bindings or len(bindings) > MAX_ITEMS:
        _fail("version_bindings must contain one to 10000 entries", "LOCAL_INPUT_LIMIT")
    names = {_identifier(name, "binding name") for name in bindings}
    if names != set(bindings):
        _fail("binding names are not canonical", "INVALID_LOCAL_INPUT")
    normalized_bindings = {name: _digest(bindings[name], f"version_bindings.{name}") for name in names}
    if set(graph_input) != names:
        _fail("dependencies must define every and only bound component", "PROVENANCE_CLOSURE_INVALID")
    graph: dict[str, tuple[str, ...]] = {}
    edge_count = 0
    for name in sorted(names):
        deps = _text_items(graph_input[name], f"dependencies.{name}")
        if name in deps or any(dep not in names for dep in deps):
            _fail("dependency graph is not closed or contains a self-edge", "PROVENANCE_CLOSURE_INVALID")
        graph[name] = tuple(sorted(deps))
        edge_count += len(deps)
    if edge_count > MAX_EDGES:
        _fail("dependency graph exceeds the edge limit", "LOCAL_INPUT_LIMIT")

    indegree = {name: len(graph[name]) for name in names}
    dependents: dict[str, list[str]] = {name: [] for name in names}
    for name, deps in graph.items():
        for dependency in deps:
            dependents[dependency].append(name)
    ready = [name for name, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for dependent in dependents[name]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(order) != len(names):
        _fail("dependency graph contains a cycle", "PROVENANCE_CYCLE")
    material = {
        "bindings": {name: normalized_bindings[name] for name in sorted(names)},
        "dependencies": {name: list(graph[name]) for name in sorted(names)},
    }
    return {
        "binding_count": len(names),
        "dependency_edge_count": edge_count,
        "topological_order": tuple(order),
        "receipt_digest": digest_object(material, domain="local-provenance-bindings"),
    }


def progressive_disclosure(
    skill_metadata: Sequence[object],
    context: Mapping[str, object],
    query_terms: Sequence[object],
    context_budget_tokens: int,
) -> dict[str, object]:
    """Filter scoped Skill metadata and greedily disclose within a token budget."""

    _bound(
        "progressive disclosure",
        {
            "skill_metadata": skill_metadata,
            "context": context,
            "query_terms": query_terms,
            "context_budget_tokens": context_budget_tokens,
        },
    )
    records = _sequence(skill_metadata, "skill_metadata")
    ctx = _mapping(context, "context")
    _exact_keys(
        ctx,
        frozenset({"tenant_id", "project_id", "environment", "permissions"}),
    )
    tenant = _identifier(ctx["tenant_id"], "context.tenant_id")
    project = _identifier(ctx["project_id"], "context.project_id")
    environment = _identifier(ctx["environment"], "context.environment")
    permissions = frozenset(_text_items(ctx["permissions"], "context.permissions"))
    terms = tuple(sorted(term.casefold() for term in _text_items(query_terms, "query_terms")))
    if len(terms) > MAX_QUERY_TERMS:
        _fail(
            f"query_terms exceeds {MAX_QUERY_TERMS} terms",
            "LOCAL_INPUT_LIMIT",
        )
    budget = _integer(context_budget_tokens, "context_budget_tokens", minimum=1, maximum=1_000_000)
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    required = frozenset(
        {"id", "summary", "tags", "tokens", "tenant_id", "project_id", "environment", "permissions"}
    )
    for index, item in enumerate(records):
        record = _mapping(item, f"skill_metadata[{index}]")
        _exact_keys(record, required)
        skill_id = _identifier(record["id"], f"skill_metadata[{index}].id")
        if skill_id in seen:
            _fail("skill metadata contains duplicate ids", "DUPLICATE_LOCAL_INPUT")
        seen.add(skill_id)
        summary = _text(record["summary"], f"skill_metadata[{index}].summary", allow_empty=True)
        tags = _text_items(record["tags"], f"skill_metadata[{index}].tags")
        tokens = _integer(
            record["tokens"],
            f"skill_metadata[{index}].tokens",
            minimum=1,
            maximum=1_000_000,
        )
        record_tenant = _identifier(record["tenant_id"], f"skill_metadata[{index}].tenant_id")
        record_project = _identifier(record["project_id"], f"skill_metadata[{index}].project_id")
        record_environment = _identifier(record["environment"], f"skill_metadata[{index}].environment")
        required_permissions = frozenset(
            _text_items(record["permissions"], f"skill_metadata[{index}].permissions")
        )
        if record_tenant not in {"*", tenant} or record_project not in {"*", project}:
            continue
        if record_environment not in {"*", environment} or not required_permissions <= permissions:
            continue
        haystack = " ".join((skill_id, summary, *tags)).casefold()
        score = sum(1 for term in terms if term in haystack)
        if terms and score == 0:
            continue
        candidates.append((score, tokens, skill_id))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected: list[str] = []
    deferred: list[str] = []
    used = 0
    for _score, tokens, skill_id in candidates:
        if used + tokens <= budget:
            selected.append(skill_id)
            used += tokens
        else:
            deferred.append(skill_id)
    result_material = {"selected": selected, "deferred": deferred, "used": used, "budget": budget}
    return {
        "selected_skill_ids": tuple(selected),
        "deferred_skill_ids": tuple(deferred),
        "used_tokens": used,
        "budget_tokens": budget,
        "selection_digest": digest_object(result_material, domain="local-progressive-disclosure"),
    }


def route_constrained_candidate(
    candidates: Sequence[object],
    constraints: Mapping[str, object],
) -> dict[str, object]:
    """Choose deterministically after enforcing capability and proof constraints."""

    _bound("candidate routing", {"candidates": candidates, "constraints": constraints})
    records = _sequence(candidates, "candidates")
    limits = _mapping(constraints, "constraints")
    _exact_keys(
        limits,
        frozenset(
            {"required_capabilities", "max_cost", "max_latency_ms", "min_quality", "min_proof", "max_risk"}
        ),
    )
    required_capabilities = frozenset(
        _text_items(limits["required_capabilities"], "constraints.required_capabilities")
    )
    max_cost = _decimal(limits["max_cost"], "constraints.max_cost", minimum=Decimal(0))
    max_latency = _integer(limits["max_latency_ms"], "constraints.max_latency_ms", maximum=86_400_000)
    min_quality = _decimal(limits["min_quality"], "constraints.min_quality", minimum=Decimal(0))
    min_proof = _integer(limits["min_proof"], "constraints.min_proof", maximum=5)
    max_risk = _integer(limits["max_risk"], "constraints.max_risk", maximum=100)
    eligible: list[tuple[int, int, Decimal, Decimal, int, str]] = []
    seen: set[str] = set()
    required = frozenset({"id", "capabilities", "cost", "latency_ms", "quality", "proof", "risk"})
    for index, item in enumerate(records):
        record = _mapping(item, f"candidates[{index}]")
        _exact_keys(record, required)
        candidate_id = _identifier(record["id"], f"candidates[{index}].id")
        if candidate_id in seen:
            _fail("candidate ids must be unique", "DUPLICATE_LOCAL_INPUT")
        seen.add(candidate_id)
        capabilities = frozenset(_text_items(record["capabilities"], f"candidates[{index}].capabilities"))
        cost = _decimal(record["cost"], f"candidates[{index}].cost", minimum=Decimal(0))
        latency = _integer(record["latency_ms"], f"candidates[{index}].latency_ms", maximum=86_400_000)
        quality = _decimal(record["quality"], f"candidates[{index}].quality", minimum=Decimal(0))
        proof = _integer(record["proof"], f"candidates[{index}].proof", maximum=5)
        risk = _integer(record["risk"], f"candidates[{index}].risk", maximum=100)
        if (
            required_capabilities <= capabilities
            and cost <= max_cost
            and latency <= max_latency
            and quality >= min_quality
            and proof >= min_proof
            and risk <= max_risk
        ):
            eligible.append((risk, -proof, -quality, cost, latency, candidate_id))
    if not eligible:
        _fail("no candidate satisfies every hard constraint", "NO_FEASIBLE_CANDIDATE")
    eligible.sort()
    selected = eligible[0][-1]
    eligible_ids = tuple(sorted(item[-1] for item in eligible))
    return {
        "selected_id": selected,
        "eligible_ids": eligible_ids,
        "decision_digest": digest_object(
            {"selected": selected, "eligible": eligible_ids},
            domain="local-constrained-router",
        ),
    }


def _typed_graph(
    nodes: Sequence[object], edges: Sequence[object]
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    node_items = _text_items(nodes, "nodes")
    if not node_items:
        _fail("graph must have at least one node", "INVALID_GRAPH")
    edge_items = _sequence(edges, "edges")
    if len(edge_items) > MAX_EDGES:
        _fail("graph exceeds the edge limit", "LOCAL_INPUT_LIMIT")
    node_set = set(node_items)
    normalized_edges: set[tuple[str, str]] = set()
    for index, item in enumerate(edge_items):
        edge = _mapping(item, f"edges[{index}]")
        _exact_keys(edge, frozenset({"source", "target"}))
        source = _identifier(edge["source"], f"edges[{index}].source")
        target = _identifier(edge["target"], f"edges[{index}].target")
        if source not in node_set or target not in node_set or source == target:
            _fail("graph has a dangling or self edge", "INVALID_GRAPH")
        pair = (source, target)
        if pair in normalized_edges:
            _fail("graph contains duplicate edges", "DUPLICATE_LOCAL_INPUT")
        normalized_edges.add(pair)
    return tuple(sorted(node_set)), tuple(sorted(normalized_edges))


def typed_graph_closure(
    nodes: Sequence[object],
    edges: Sequence[object],
    seeds: Sequence[object],
) -> dict[str, object]:
    """Compute a bounded forward transitive closure on an exact directed graph."""

    _bound("typed graph closure", {"nodes": nodes, "edges": edges, "seeds": seeds})
    node_items, edge_items = _typed_graph(nodes, edges)
    seed_items = _text_items(seeds, "seeds")
    if not seed_items or any(seed not in set(node_items) for seed in seed_items):
        _fail("seeds must be non-empty graph nodes", "INVALID_GRAPH")
    adjacency: dict[str, list[str]] = {node: [] for node in node_items}
    for source, target in edge_items:
        adjacency[source].append(target)
    visited = set(seed_items)
    queue = deque(sorted(seed_items))
    while queue:
        source = queue.popleft()
        for target in adjacency[source]:
            if target not in visited:
                visited.add(target)
                if len(visited) > MAX_ITEMS:
                    _fail("graph closure exceeds the node limit", "LOCAL_INPUT_LIMIT")
                queue.append(target)
    affected = tuple(sorted(visited))
    return {
        "affected_nodes": affected,
        "affected_count": len(affected),
        "closure_digest": digest_object(affected, domain="local-typed-graph-closure"),
    }


def select_affected_tests(
    nodes: Sequence[object],
    edges: Sequence[object],
    changed_nodes: Sequence[object],
    coverage: Mapping[str, object],
    critical_nodes: Sequence[object],
) -> dict[str, object]:
    """Select tests from the affected closure and expose uncovered critical nodes."""

    _bound(
        "affected tests",
        {
            "nodes": nodes,
            "edges": edges,
            "changed_nodes": changed_nodes,
            "coverage": coverage,
            "critical_nodes": critical_nodes,
        },
    )
    closure = typed_graph_closure(nodes, edges, changed_nodes)
    affected = cast(tuple[str, ...], closure["affected_nodes"])
    node_set = set(_text_items(nodes, "nodes"))
    critical = set(_text_items(critical_nodes, "critical_nodes"))
    if not critical <= node_set:
        _fail("critical_nodes must belong to the graph", "INVALID_GRAPH")
    coverage_map = _mapping(coverage, "coverage")
    if any(node not in node_set for node in coverage_map):
        _fail("coverage contains a node outside the graph", "INVALID_GRAPH")
    normalized_coverage = {
        node: _text_items(value, f"coverage.{node}") for node, value in coverage_map.items()
    }
    selected = sorted({test for node in affected for test in normalized_coverage.get(node, ())})
    uncovered = sorted(node for node in affected if node in critical and not normalized_coverage.get(node))
    return {
        "affected_nodes": affected,
        "selected_tests": tuple(selected),
        "uncovered_critical_nodes": tuple(uncovered),
        "confidence": "INCOMPLETE" if uncovered else "BOUNDED_HIGH",
        "selection_digest": digest_object(
            {"affected": affected, "selected": selected, "uncovered": uncovered},
            domain="local-affected-test-selection",
        ),
    }


def dependency_closed_slice(
    nodes: Sequence[object],
    dependency_edges: Sequence[object],
    focus_nodes: Sequence[object],
    token_costs: Mapping[str, object],
    token_budget: int,
) -> dict[str, object]:
    """Build an all-or-fail dependency-closed context slice."""

    _bound(
        "dependency slice",
        {
            "nodes": nodes,
            "dependency_edges": dependency_edges,
            "focus_nodes": focus_nodes,
            "token_costs": token_costs,
            "token_budget": token_budget,
        },
    )
    closure = typed_graph_closure(nodes, dependency_edges, focus_nodes)
    selected = cast(tuple[str, ...], closure["affected_nodes"])
    costs = _mapping(token_costs, "token_costs")
    node_set = set(_text_items(nodes, "nodes"))
    if set(costs) != node_set:
        _fail("token_costs must define every and only graph node", "INVALID_SLICE_COSTS")
    normalized_costs = {
        node: _integer(cost, f"token_costs.{node}", minimum=1, maximum=1_000_000)
        for node, cost in costs.items()
    }
    budget = _integer(token_budget, "token_budget", minimum=1, maximum=10_000_000)
    used = sum(normalized_costs[node] for node in selected)
    if used > budget:
        _fail("dependency-closed slice exceeds the budget", "SLICE_BUDGET_EXCEEDED")
    return {
        "selected_nodes": selected,
        "used_tokens": used,
        "budget_tokens": budget,
        "slice_digest": digest_object(
            {"selected": selected, "costs": {node: normalized_costs[node] for node in selected}},
            domain="local-dependency-closed-slice",
        ),
    }


def classify_monotonic_risk(
    affected_nodes: Sequence[object],
    critical_nodes: Sequence[object],
    runtime_hot_paths: Sequence[object],
    security_boundaries: Sequence[object],
    historical_failures: int,
    proof_coverage: object,
) -> dict[str, object]:
    """Compute a deterministic risk score whose adverse inputs are monotonic."""

    _bound(
        "risk classification",
        {
            "affected_nodes": affected_nodes,
            "critical_nodes": critical_nodes,
            "runtime_hot_paths": runtime_hot_paths,
            "security_boundaries": security_boundaries,
            "historical_failures": historical_failures,
            "proof_coverage": str(proof_coverage),
        },
    )
    affected = set(_text_items(affected_nodes, "affected_nodes"))
    critical = set(_text_items(critical_nodes, "critical_nodes"))
    hot = set(_text_items(runtime_hot_paths, "runtime_hot_paths"))
    security = set(_text_items(security_boundaries, "security_boundaries"))
    if not critical <= affected or not hot <= affected or not security <= affected:
        _fail("risk dimensions must be subsets of affected_nodes", "INVALID_RISK_INPUT")
    failures = _integer(historical_failures, "historical_failures", maximum=1_000_000)
    coverage = _decimal(proof_coverage, "proof_coverage", minimum=Decimal(0))
    if coverage > 1:
        _fail("proof_coverage must be within [0,1]", "INVALID_RISK_INPUT")
    score_decimal = (
        Decimal(min(len(affected), 20))
        + Decimal(min(len(critical), 4) * 15)
        + Decimal(min(len(hot), 4) * 6)
        + Decimal(min(len(security), 4) * 10)
        + Decimal(min(failures, 10) * 2)
        + (Decimal(1) - coverage) * Decimal(30)
    )
    score = min(100, int(score_decimal.to_integral_value(rounding="ROUND_CEILING")))
    level = "CRITICAL" if score >= 80 else "HIGH" if score >= 55 else "MEDIUM" if score >= 25 else "LOW"
    return {
        "score": score,
        "level": level,
        "model_version": "local-risk-v1",
        "input_digest": digest_object(
            {
                "affected": sorted(affected),
                "critical": sorted(critical),
                "hot": sorted(hot),
                "security": sorted(security),
                "failures": failures,
                "proof_coverage": _decimal_text(coverage),
            },
            domain="local-monotonic-risk",
        ),
    }


def build_explainability_ledger(edits: Sequence[object]) -> dict[str, object]:
    """Validate and hash-chain exact edit explanations in explicit sequence order."""

    _bound("explainability ledger", edits)
    records = _sequence(edits, "edits")
    if not records:
        _fail("edits must not be empty", "INVALID_LEDGER")
    required = frozenset(
        {
            "sequence",
            "edit_id",
            "path_digest",
            "before_digest",
            "after_digest",
            "rule_id",
            "reason",
            "source_evidence_digests",
            "assumptions",
            "validation_digests",
            "rollback_digest",
        }
    )
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(records):
        record = _mapping(item, f"edits[{index}]")
        _exact_keys(record, required)
        edit_id = _identifier(record["edit_id"], f"edits[{index}].edit_id")
        if edit_id in seen_ids:
            _fail("edit ids must be unique", "DUPLICATE_LOCAL_INPUT")
        seen_ids.add(edit_id)
        source_evidence = tuple(
            sorted(
                _digest(value, f"edits[{index}].source_evidence_digests[]")
                for value in _sequence(record["source_evidence_digests"], "source_evidence_digests")
            )
        )
        validations = tuple(
            sorted(
                _digest(value, f"edits[{index}].validation_digests[]")
                for value in _sequence(record["validation_digests"], "validation_digests")
            )
        )
        if not source_evidence or not validations:
            _fail("ledger entries require source evidence and validation", "INVALID_LEDGER")
        assumptions = tuple(
            sorted(_text(value, "assumption") for value in _sequence(record["assumptions"], "assumptions"))
        )
        normalized.append(
            {
                "sequence": _integer(record["sequence"], f"edits[{index}].sequence"),
                "edit_id": edit_id,
                "path_digest": _digest(record["path_digest"], "path_digest"),
                "before_digest": _digest(record["before_digest"], "before_digest"),
                "after_digest": _digest(record["after_digest"], "after_digest"),
                "rule_id": _identifier(record["rule_id"], "rule_id"),
                "reason_digest": digest_object(_text(record["reason"], "reason"), domain="ledger-reason"),
                "source_evidence_digests": source_evidence,
                "assumptions_digest": digest_object(assumptions, domain="ledger-assumptions"),
                "validation_digests": validations,
                "rollback_digest": _digest(record["rollback_digest"], "rollback_digest"),
            }
        )
    normalized.sort(key=lambda item: cast(int, item["sequence"]))
    if [item["sequence"] for item in normalized] != list(range(len(normalized))):
        _fail("ledger sequences must be contiguous from zero", "INVALID_LEDGER_SEQUENCE")
    previous: str | None = None
    chained: list[dict[str, object]] = []
    for record in normalized:
        entry_digest = digest_object(
            {"previous_digest": previous, "record": record},
            domain="local-explainability-ledger-entry",
        )
        chained.append({**record, "previous_digest": previous, "entry_digest": entry_digest})
        previous = entry_digest
    return {
        "entry_count": len(chained),
        "entries": tuple(chained),
        "ledger_digest": previous,
    }


def lineage_impact_closure(
    entities: Sequence[object],
    lineage_edges: Sequence[object],
    changed_entities: Sequence[object],
) -> dict[str, object]:
    """Compute downstream impact across a typed dataset/table/column lineage graph."""

    _bound(
        "lineage impact",
        {"entities": entities, "lineage_edges": lineage_edges, "changed_entities": changed_entities},
    )
    entity_records = _sequence(entities, "entities")
    entity_kinds: dict[str, str] = {}
    for index, item in enumerate(entity_records):
        record = _mapping(item, f"entities[{index}]")
        _exact_keys(record, frozenset({"id", "kind"}))
        entity_id = _identifier(record["id"], f"entities[{index}].id")
        kind = _identifier(record["kind"], f"entities[{index}].kind")
        if kind not in _KINDS or entity_id in entity_kinds:
            _fail("lineage entities require unique ids and supported kinds", "INVALID_LINEAGE")
        entity_kinds[entity_id] = kind
    edge_records = _sequence(lineage_edges, "lineage_edges")
    plain_edges: list[dict[str, object]] = []
    for index, item in enumerate(edge_records):
        record = _mapping(item, f"lineage_edges[{index}]")
        _exact_keys(record, frozenset({"source", "target", "kind"}))
        edge_kind = _identifier(record["kind"], f"lineage_edges[{index}].kind")
        if edge_kind not in _KINDS:
            _fail("lineage edge kind is unsupported", "INVALID_LINEAGE")
        source = _identifier(record["source"], f"lineage_edges[{index}].source")
        target = _identifier(record["target"], f"lineage_edges[{index}].target")
        if entity_kinds.get(source) != edge_kind or entity_kinds.get(target) != edge_kind:
            _fail("lineage edge kind must match both endpoint kinds", "INVALID_LINEAGE")
        plain_edges.append({"source": source, "target": target})
    closure = typed_graph_closure(tuple(entity_kinds), plain_edges, changed_entities)
    impacted = cast(tuple[str, ...], closure["affected_nodes"])
    changed = set(_text_items(changed_entities, "changed_entities"))
    consumers = tuple(entity for entity in impacted if entity not in changed)
    return {
        "impacted_entities": impacted,
        "affected_consumers": consumers,
        "entity_kinds": {entity: entity_kinds[entity] for entity in impacted},
        "impact_digest": digest_object(
            {"impacted": impacted, "kinds": {entity: entity_kinds[entity] for entity in impacted}},
            domain="local-lineage-impact",
        ),
    }


def _normalized_row(row: object, label: str) -> dict[str, object]:
    value = _mapping(row, label)
    if not value or len(value) > 256:
        _fail(f"{label} must contain one to 256 fields", "LOCAL_INPUT_LIMIT")
    result: dict[str, object] = {}
    for key, item in value.items():
        _text(key, f"{label} key")
        if isinstance(item, Decimal):
            result[key] = _decimal_text(_decimal(item, f"{label}.{key}"))
        elif item is None or isinstance(item, (str, bool, int)):
            result[key] = item
        else:
            _fail(f"{label}.{key} is not a supported scalar", "INVALID_RECONCILIATION_ROW")
    return result


def reconcile_keyed_rows(
    source_rows: Sequence[object],
    target_rows: Sequence[object],
    key_fields: Sequence[object],
    decimal_fields: Sequence[object] = (),
) -> dict[str, object]:
    """Compare keyed row multisets and exact Decimal aggregates without floats."""

    if len(source_rows) > MAX_ITEMS or len(target_rows) > MAX_ITEMS:
        _fail("row set exceeds the local reconciliation limit", "LOCAL_INPUT_LIMIT")
    keys = _text_items(key_fields, "key_fields")
    decimals = _text_items(decimal_fields, "decimal_fields")
    if not keys:
        _fail("key_fields must not be empty", "INVALID_RECONCILIATION_ROW")
    source = tuple(_normalized_row(row, f"source_rows[{index}]") for index, row in enumerate(source_rows))
    target = tuple(_normalized_row(row, f"target_rows[{index}]") for index, row in enumerate(target_rows))
    _bound(
        "row reconciliation",
        {"source_rows": source, "target_rows": target, "key_fields": keys, "decimal_fields": decimals},
    )

    def analyze(
        rows: Sequence[Mapping[str, object]], label: str
    ) -> tuple[Counter[str], Counter[str], dict[str, Counter[str]], dict[str, Decimal]]:
        row_counter: Counter[str] = Counter()
        key_counter: Counter[str] = Counter()
        keyed_rows: dict[str, Counter[str]] = {}
        aggregates = {field: Decimal(0) for field in decimals}
        for index, row in enumerate(rows):
            if any(field not in row for field in (*keys, *decimals)):
                _fail(f"{label}[{index}] lacks a required key or decimal field", "INVALID_RECONCILIATION_ROW")
            key_material = {field: row[field] for field in keys}
            key_digest = digest_object(key_material, domain="local-reconciliation-key")
            row_digest = digest_object(row, domain="local-reconciliation-row")
            key_counter[key_digest] += 1
            row_counter[row_digest] += 1
            keyed_rows.setdefault(key_digest, Counter())[row_digest] += 1
            for field in decimals:
                aggregates[field] += _decimal(row[field], f"{label}[{index}].{field}")
        return row_counter, key_counter, keyed_rows, aggregates

    source_counter, source_keys, source_keyed_rows, source_aggregates = analyze(source, "source_rows")
    target_counter, target_keys, target_keyed_rows, target_aggregates = analyze(target, "target_rows")
    missing = tuple(sorted((source_counter - target_counter).elements()))
    unexpected = tuple(sorted((target_counter - source_counter).elements()))
    missing_keys = tuple(sorted((source_keys - target_keys).elements()))
    unexpected_keys = tuple(sorted((target_keys - source_keys).elements()))
    mismatched_keys = tuple(
        sorted(
            key_digest
            for key_digest in set(source_keyed_rows) | set(target_keyed_rows)
            if source_keyed_rows.get(key_digest, Counter()) != target_keyed_rows.get(key_digest, Counter())
        )
    )
    aggregate_deltas = {
        field: _decimal_text(target_aggregates[field] - source_aggregates[field])
        for field in sorted(decimals)
    }
    duplicates = {
        "source": sum(count - 1 for count in source_keys.values() if count > 1),
        "target": sum(count - 1 for count in target_keys.values() if count > 1),
    }
    equivalent = not missing and not unexpected and all(delta == "0" for delta in aggregate_deltas.values())
    return {
        "source_count": len(source),
        "target_count": len(target),
        "missing_row_digests": missing,
        "unexpected_row_digests": unexpected,
        "missing_key_digests": missing_keys,
        "unexpected_key_digests": unexpected_keys,
        "mismatched_key_digests": mismatched_keys,
        "duplicate_key_rows": duplicates,
        "aggregate_deltas": aggregate_deltas,
        "equivalent": equivalent,
        "reconciliation_digest": digest_object(
            {
                "missing": missing,
                "unexpected": unexpected,
                "missing_keys": missing_keys,
                "unexpected_keys": unexpected_keys,
                "mismatched_keys": mismatched_keys,
                "duplicates": duplicates,
                "aggregate_deltas": aggregate_deltas,
            },
            domain="local-keyed-reconciliation",
        ),
    }


def evaluate_rubric_scorecard(
    observations: Mapping[str, object],
    rubric: Sequence[object],
) -> dict[str, object]:
    """Evaluate versioned normalized metrics with mandatory fail-closed gates."""

    _bound("rubric scorecard", {"observations": observations, "rubric": rubric})
    values_input = _mapping(observations, "observations")
    records = _sequence(rubric, "rubric")
    if not records:
        _fail("rubric must not be empty", "INVALID_RUBRIC")
    normalized_values = {
        _identifier(name, "observation name"): _decimal(value, f"observations.{name}", minimum=Decimal(0))
        for name, value in values_input.items()
    }
    required = frozenset({"metric", "weight", "minimum", "mandatory"})
    normalized_rubric: list[tuple[str, Decimal, Decimal, bool]] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        record = _mapping(item, f"rubric[{index}]")
        _exact_keys(record, required)
        metric = _identifier(record["metric"], f"rubric[{index}].metric")
        if metric in seen:
            _fail("rubric metrics must be unique", "DUPLICATE_LOCAL_INPUT")
        seen.add(metric)
        weight = _decimal(record["weight"], f"rubric[{index}].weight", minimum=Decimal(0))
        minimum = _decimal(record["minimum"], f"rubric[{index}].minimum", minimum=Decimal(0))
        mandatory = _boolean(record["mandatory"], f"rubric[{index}].mandatory")
        if minimum > 1:
            _fail("rubric minimum must be normalized to [0,1]", "INVALID_RUBRIC")
        normalized_rubric.append((metric, weight, minimum, mandatory))
    if set(normalized_values) != seen:
        _fail("observations must define every and only rubric metric", "INVALID_RUBRIC")
    if sum((item[1] for item in normalized_rubric), Decimal(0)) != Decimal(1):
        _fail("rubric weights must sum exactly to one", "INVALID_RUBRIC")
    if any(value > 1 for value in normalized_values.values()):
        _fail("observations must be normalized to [0,1]", "INVALID_RUBRIC")
    weighted = sum(
        (normalized_values[metric] * weight for metric, weight, _minimum, _mandatory in normalized_rubric),
        Decimal(0),
    )
    mandatory_failures = tuple(
        sorted(
            metric
            for metric, _weight, minimum, mandatory in normalized_rubric
            if mandatory and normalized_values[metric] < minimum
        )
    )
    material = {
        "observations": {name: _decimal_text(normalized_values[name]) for name in sorted(seen)},
        "rubric": [
            {
                "metric": metric,
                "weight": _decimal_text(weight),
                "minimum": _decimal_text(minimum),
                "mandatory": mandatory,
            }
            for metric, weight, minimum, mandatory in sorted(normalized_rubric)
        ],
    }
    return {
        "score": _decimal_text(weighted),
        "decision": "FAIL" if mandatory_failures else "PASS_BOUNDED_LOCAL",
        "mandatory_failures": mandatory_failures,
        "rubric_digest": digest_object(material, domain="local-rubric-scorecard"),
    }


def incident_causal_divergence(
    expected_events: Sequence[object],
    observed_events: Sequence[object],
) -> dict[str, object]:
    """Find the first causal event divergence after strict sequence validation."""

    _bound("incident replay", {"expected_events": expected_events, "observed_events": observed_events})
    required = frozenset({"sequence", "event_id", "parent_id", "kind", "payload_digest"})

    def normalize(items: Sequence[object], label: str) -> list[dict[str, object]]:
        records = _sequence(items, label)
        normalized: list[dict[str, object]] = []
        ids: set[str] = set()
        for index, item in enumerate(records):
            record = _mapping(item, f"{label}[{index}]")
            _exact_keys(record, required)
            event_id = _identifier(record["event_id"], f"{label}[{index}].event_id")
            if event_id in ids:
                _fail("event ids must be unique", "INCIDENT_REPLAY_INCONCLUSIVE")
            ids.add(event_id)
            parent_value = record["parent_id"]
            parent = (
                None if parent_value is None else _identifier(parent_value, f"{label}[{index}].parent_id")
            )
            normalized.append(
                {
                    "sequence": _integer(record["sequence"], f"{label}[{index}].sequence"),
                    "event_id": event_id,
                    "parent_id": parent,
                    "kind": _identifier(record["kind"], f"{label}[{index}].kind"),
                    "payload_digest": _digest(record["payload_digest"], f"{label}[{index}].payload_digest"),
                }
            )
        normalized.sort(key=lambda record: cast(int, record["sequence"]))
        if [record["sequence"] for record in normalized] != list(range(len(normalized))):
            _fail("event sequences must be contiguous from zero", "INCIDENT_REPLAY_INCONCLUSIVE")
        prior: set[str] = set()
        for record in normalized:
            record_parent = cast(str | None, record["parent_id"])
            if record_parent is not None and record_parent not in prior:
                _fail("event parent must reference an earlier event", "INCIDENT_REPLAY_INCONCLUSIVE")
            prior.add(cast(str, record["event_id"]))
        return normalized

    expected = normalize(expected_events, "expected_events")
    observed = normalize(observed_events, "observed_events")
    common = min(len(expected), len(observed))
    first: int | None = None
    for index in range(common):
        expected_signature = tuple(
            expected[index][key] for key in ("event_id", "parent_id", "kind", "payload_digest")
        )
        observed_signature = tuple(
            observed[index][key] for key in ("event_id", "parent_id", "kind", "payload_digest")
        )
        if expected_signature != observed_signature:
            first = index
            break
    if first is None and len(expected) != len(observed):
        first = common
    equivalent = first is None
    return {
        "equivalent": equivalent,
        "first_divergence_sequence": first,
        "expected_event_id": None if first is None or first >= len(expected) else expected[first]["event_id"],
        "observed_event_id": None if first is None or first >= len(observed) else observed[first]["event_id"],
        "comparison_digest": digest_object(
            {"expected": expected, "observed": observed, "first": first},
            domain="local-incident-divergence",
        ),
    }


def optimize_cost_latency_quality(
    candidates: Sequence[object],
    constraints: Mapping[str, object],
) -> dict[str, object]:
    """Return the deterministic Pareto frontier after non-negotiable gates."""

    _bound("cost latency quality", {"candidates": candidates, "constraints": constraints})
    records = _sequence(candidates, "candidates")
    limits = _mapping(constraints, "constraints")
    _exact_keys(limits, frozenset({"max_cost", "max_latency_ms", "min_quality", "proof_required"}))
    max_cost = _decimal(limits["max_cost"], "constraints.max_cost", minimum=Decimal(0))
    max_latency = _integer(limits["max_latency_ms"], "constraints.max_latency_ms", maximum=86_400_000)
    min_quality = _decimal(limits["min_quality"], "constraints.min_quality", minimum=Decimal(0))
    proof_required = _boolean(limits["proof_required"], "constraints.proof_required")
    required = frozenset({"id", "cost", "latency_ms", "quality", "proof_satisfied"})
    feasible: list[tuple[str, Decimal, int, Decimal]] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        record = _mapping(item, f"candidates[{index}]")
        _exact_keys(record, required)
        candidate_id = _identifier(record["id"], f"candidates[{index}].id")
        if candidate_id in seen:
            _fail("candidate ids must be unique", "DUPLICATE_LOCAL_INPUT")
        seen.add(candidate_id)
        cost = _decimal(record["cost"], f"candidates[{index}].cost", minimum=Decimal(0))
        latency = _integer(record["latency_ms"], f"candidates[{index}].latency_ms", maximum=86_400_000)
        quality = _decimal(record["quality"], f"candidates[{index}].quality", minimum=Decimal(0))
        proof = _boolean(record["proof_satisfied"], f"candidates[{index}].proof_satisfied")
        if (
            cost <= max_cost
            and latency <= max_latency
            and quality >= min_quality
            and (proof or not proof_required)
        ):
            feasible.append((candidate_id, cost, latency, quality))
    if not feasible:
        _fail("no feasible cost-latency-quality candidate", "NO_FEASIBLE_CANDIDATE")

    # Find the three-dimensional Pareto frontier in O(n log n).  Processing
    # equal-cost groups separately is important: the Fenwick tree contains only
    # strictly cheaper candidates, while a linear pass handles equal-cost
    # latency/quality dominance without treating identical metric tuples as
    # dominating one another.
    latencies = sorted({candidate[2] for candidate in feasible})
    latency_index = {latency: index + 1 for index, latency in enumerate(latencies)}
    fenwick: list[Decimal | None] = [None] * (len(latencies) + 1)

    def best_quality_at_or_below(latency: int) -> Decimal | None:
        index = latency_index[latency]
        best: Decimal | None = None
        while index:
            value = fenwick[index]
            if value is not None and (best is None or value > best):
                best = value
            index -= index & -index
        return best

    def record_quality(latency: int, quality: Decimal) -> None:
        index = latency_index[latency]
        while index < len(fenwick):
            value = fenwick[index]
            if value is None or quality > value:
                fenwick[index] = quality
            index += index & -index

    frontier: list[tuple[str, Decimal, int, Decimal]] = []
    by_cost = sorted(feasible, key=lambda item: (item[1], item[2], -item[3], item[0]))
    start = 0
    while start < len(by_cost):
        end = start + 1
        while end < len(by_cost) and by_cost[end][1] == by_cost[start][1]:
            end += 1
        cost_group = by_cost[start:end]
        lower_latency_best: Decimal | None = None
        latency_start = 0
        while latency_start < len(cost_group):
            latency_end = latency_start + 1
            latency = cost_group[latency_start][2]
            while latency_end < len(cost_group) and cost_group[latency_end][2] == latency:
                latency_end += 1
            latency_group = cost_group[latency_start:latency_end]
            same_latency_best = max(candidate[3] for candidate in latency_group)
            cheaper_best = best_quality_at_or_below(latency)
            for candidate in latency_group:
                quality = candidate[3]
                dominated_by_cheaper = cheaper_best is not None and cheaper_best >= quality
                dominated_by_lower_latency = (
                    lower_latency_best is not None and lower_latency_best >= quality
                )
                dominated_at_same_latency = same_latency_best > quality
                if not (
                    dominated_by_cheaper
                    or dominated_by_lower_latency
                    or dominated_at_same_latency
                ):
                    frontier.append(candidate)
            if lower_latency_best is None or same_latency_best > lower_latency_best:
                lower_latency_best = same_latency_best
            latency_start = latency_end
        for _candidate_id, _cost, latency, quality in cost_group:
            record_quality(latency, quality)
        start = end
    frontier.sort(key=lambda item: (-item[3], item[1], item[2], item[0]))
    selected = frontier[0][0]
    frontier_ids = tuple(item[0] for item in sorted(frontier, key=lambda item: item[0]))
    return {
        "selected_id": selected,
        "pareto_frontier_ids": frontier_ids,
        "feasible_count": len(feasible),
        "decision_digest": digest_object(
            {"selected": selected, "frontier": frontier_ids},
            domain="local-cost-latency-quality",
        ),
    }
